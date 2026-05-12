"""
ClimaSync Collection Service — Open-Meteo Weather Collector

Polls Open-Meteo API for weather forecasts for all Pakistan locations.

Key responsibilities:
  - Check every 15 minutes which locations are due for polling
  - Sort by poll_priority (critical first)
  - Fetch hourly and daily weather data using BATCH API (multiple locations per call)
  - Track cycle metrics per location
  - Update poll state after each successful collection

OPTIMIZATION: Uses Open-Meteo's batch endpoint to fetch up to 10 locations
per API call, reducing total API calls by 10x.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx

from app.collectors.base_collector import BaseCollector
from app.core.config import get_settings
from app.core.exceptions import ApiResponseError
from app.core.logger import get_logger
from app.models.reference_models import PakistanLocation
from app.repositories.cycle_repository import CycleRepository
from app.repositories.reference_repository import ReferenceRepository
from app.services.openmeteo_service import OpenMeteoService

logger = get_logger(__name__)
settings = get_settings()

# Pakistan Standard Time
_PKT = ZoneInfo("Asia/Karachi")

# Open-Meteo batch API allows up to 10 locations per request
_BATCH_SIZE = 10


class OpenMeteoCollector(BaseCollector):
    """Collects weather forecast data from Open-Meteo API.
    
    Inherits HTTP client, retry logic, and rate limit handling from BaseCollector.
    """

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        reference_repo: ReferenceRepository,
        cycle_repo: CycleRepository,
        openmeteo_service: OpenMeteoService,
        pakistan_locations: list[PakistanLocation],
    ) -> None:
        """Initialize Open-Meteo collector.
        
        Args:
            http_client: Shared async HTTP client.
            reference_repo: Repository for API config and backoff.
            cycle_repo: Repository for cycle tracking.
            openmeteo_service: Service for parsing and processing weather data.
            pakistan_locations: List of all Pakistan monitoring locations.
        """
        super().__init__(
            api_name="open_meteo",
            http_client=http_client,
            reference_repo=reference_repo,
        )
        
        self.cycle_repo = cycle_repo
        self.openmeteo_service = openmeteo_service
        self.pakistan_locations = pakistan_locations
        
        logger.info("OpenMeteoCollector initialized with %d locations", len(pakistan_locations))

    # ── Location Filtering ────────────────────────────────────────

    async def get_due_locations(self) -> list[PakistanLocation]:
        """Get locations that are due for polling.
        
        Fetches directly from the database to ensure we have the most
        up-to-date next_poll_due_at timestamps.
        
        Returns:
            List of locations due for polling, sorted by priority.
        """
        due_locations = await self.reference_repo.get_due_locations()
        
        logger.info(
            "Found %d locations due for polling (out of %d total active)",
            len(due_locations),
            sum(1 for loc in self.pakistan_locations if loc.is_active)
        )
        return due_locations

    # ── Batch Location Collection ─────────────────────────────────

    async def collect_batch(
        self,
        locations: list[PakistanLocation],
        cycle_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Collect weather data for multiple locations in a single API call.
        
        Open-Meteo supports batch requests with multiple lat/lon pairs.
        This reduces API calls by 10x (up to 10 locations per request).
        
        Args:
            locations: List of Pakistan locations (max 10).
            cycle_id: Unique ID for current collection cycle.
        
        Returns:
            Dictionary with batch collection statistics.
        """
        if len(locations) > _BATCH_SIZE:
            raise ValueError(f"Batch size cannot exceed {_BATCH_SIZE} locations")
        
        stats = {
            "locations_attempted": len(locations),
            "locations_success": 0,
            "locations_failed": 0,
            "total_hourly": 0,
            "total_daily": 0,
            "total_breaches": 0,
            "latency_ms": 0.0,
            "errors": {},
        }
        
        poll_start_time = datetime.now(_PKT)
        
        try:
            # Build batch query parameters
            batch_params = self.openmeteo_service.build_batch_params(locations)
            
            # Fetch batch data (single API call for all locations)
            response = await self.get(
                url=settings.openmeteo_base_url,
                params=batch_params,
            )
            stats["latency_ms"] = (datetime.now(_PKT) - poll_start_time).total_seconds() * 1000
            batch_data = response.json()
            
            # Check for API-level errors even if HTTP status was 200
            if isinstance(batch_data, dict) and batch_data.get("error"):
                raise ApiResponseError(
                    self.api_name,
                    response.status_code,
                    f"Open-Meteo API Error: {batch_data.get('reason', 'Unknown error')}"
                )
            
            # Parse and process each location's data
            for i, location in enumerate(locations):
                try:
                    logger.info("Polling %s [%s] (priority=%s)", location.location_name, location.location_key, location.poll_priority)
                    
                    # Extract this location's data from batch response
                    location_data = self._extract_location_data(batch_data, i)
                    
                    # Parse hourly and daily data
                    hourly_records = self.openmeteo_service.parse_hourly(
                        location_data, 
                        location
                    )
                    daily_summaries = self.openmeteo_service.parse_daily(
                        location_data, 
                        location
                    )
                    
                    logger.debug(
                        "Open-Meteo response: %d hourly, %d daily [latency=%dms]",
                        len(hourly_records),
                        len(daily_summaries),
                        latency_ms
                    )
                    
                    # Compute data freshness
                    poll_end_time = datetime.now(_PKT)
                    data_freshness_minutes = int(
                        (poll_end_time - poll_start_time).total_seconds() / 60
                    )
                    
                    # Process data (check breaches, UPSERT to database)
                    process_stats = await self.openmeteo_service.process_location(
                        hourly_records=hourly_records,
                        daily_summaries=daily_summaries,
                        cycle_id=cycle_id,
                        data_freshness_minutes=data_freshness_minutes,
                    )
                    
                    # Update poll state in database
                    await self._update_poll_state(
                        location=location,
                        success=True,
                        poll_time=poll_end_time,
                    )
                    
                    stats["locations_success"] += 1
                    stats["total_hourly"] += process_stats["hourly_upserted"]
                    stats["total_daily"] += process_stats["daily_upserted"]
                    stats["total_breaches"] += process_stats["breaches_detected"]
                    
                    logger.info(
                        "Wrote %d weather rows for %s [breaches=%d]",
                        process_stats["hourly_upserted"] + process_stats["daily_upserted"],
                        location.location_name,
                        process_stats["breaches_detected"],
                    )
                    
                except Exception as e:
                    logger.warning(
                        "Weather poll failed for %s: %s",
                        location.location_name,
                        str(e)
                    )
                    stats["locations_failed"] += 1
                    stats["errors"][location.location_name] = str(e)
                    
                    # Update poll state as failed
                    await self._update_poll_state(
                        location=location,
                        success=False,
                        poll_time=datetime.now(_PKT),
                    )
                    continue
            
        except ApiResponseError as e:
            logger.error("Batch API error: %s", str(e))
            # Mark all locations as failed
            for location in locations:
                stats["locations_failed"] += 1
                stats["errors"][location.location_name] = str(e)
                await self._update_poll_state(
                    location=location,
                    success=False,
                    poll_time=datetime.now(_PKT),
                )
            
        except Exception as e:
            logger.error("Unexpected batch error: %s", str(e))
            # Mark all locations as failed
            for location in locations:
                stats["locations_failed"] += 1
                stats["errors"][location.location_name] = str(e)
                await self._update_poll_state(
                    location=location,
                    success=False,
                    poll_time=datetime.now(_PKT),
                )
        
        return stats

    def _extract_location_data(
        self, 
        batch_data: dict[str, Any], 
        index: int
    ) -> dict[str, Any]:
        """Extract single location's data from batch response.
        
        Open-Meteo batch response structure:
        - If single location: returns normal response
        - If multiple locations: returns array of responses
        
        Args:
            batch_data: Full batch API response.
            index: Index of location in batch (0-based).
        
        Returns:
            Single location's weather data.
        """
        # Check if response is an array (multiple locations)
        if isinstance(batch_data, list):
            return batch_data[index]
        
        # Single location response
        if index == 0:
            return batch_data
        
        raise ValueError(f"Cannot extract index {index} from single-location response")

    async def _update_poll_state(
        self,
        location: PakistanLocation,
        success: bool,
        poll_time: datetime,
    ) -> None:
        """Update location's poll state in database after collection attempt.
        
        Updates:
        - last_polled_at: timestamp of this poll
        - last_poll_outcome: 'success' or 'failed'
        - next_poll_due_at: poll_time + poll_interval_minutes
        - consecutive_failures: increment on failure, reset on success
        
        Args:
            location: Location that was polled.
            success: Whether poll succeeded.
            poll_time: When the poll completed.
        """
        try:
            # Get poll interval (default to 180 minutes if not set)
            poll_interval_minutes = getattr(location, 'poll_interval_minutes', 180)
            
            # Calculate next poll time
            next_poll_due_at = poll_time + timedelta(minutes=poll_interval_minutes)
            
            # Determine outcome
            outcome = "success" if success else "failed"
            
            # Update database
            await self.reference_repo.update_location_poll_state(
                location_id=location.location_id,
                last_polled_at=poll_time,
                last_poll_outcome=outcome,
                next_poll_due_at=next_poll_due_at,
                reset_failures=success,
            )
            
            logger.debug(
                "Updated poll state for %s: outcome=%s, next_due=%s",
                location.location_name,
                outcome,
                next_poll_due_at.strftime("%Y-%m-%d %H:%M:%S %Z"),
            )
            
        except Exception as e:
            logger.error(
                "Failed to update poll state for %s: %s",
                location.location_name,
                str(e)
            )

    # ── Collection Cycle ──────────────────────────────────────────

    async def collect(self) -> dict[str, Any]:
        """Execute one Open-Meteo collection cycle.
        
        Polls all due locations using batch API (up to 10 locations per call).
        This reduces API calls by 10x compared to individual requests.
        
        Returns:
            Dictionary with cycle statistics.
        """
        # Load API config to get api_id
        api_config = await self._load_api_config()
        
        # Start cycle tracking
        cycle_start_time = datetime.now(_PKT)
        cycle_id = await self.cycle_repo.start_cycle(str(api_config.api_id), self.api_name, cycle_type="scheduled")
        
        logger.info("Weather collection cycle starting [cycle_id=%s]", cycle_id)
        
        # Reset counters
        self.reset_counters()
        
        cycle_status = "completed"
        total_hourly = 0
        total_daily = 0
        total_breaches = 0
        error_message = None
        error_summary = {}
        total_latency = 0.0
        api_calls_made = 0
        
        try:
            # Check backoff BEFORE proceeding
            if await self._check_backoff():
                logger.warning("Open-Meteo API is in backoff. Skipping cycle.")
                cycle_status = "skipped"
                error_message = "API in backoff period"
                return {
                    "cycle_id": cycle_id,
                    "status": "skipped",
                    "error": "API in backoff period",
                }
            
            # Get locations due for polling (sorted by priority)
            due_locations = await self.get_due_locations()
            self.locations_targeted = len(due_locations)
            
            if not due_locations:
                logger.info("No locations due for polling")
                cycle_status = "skipped"
            else:
                logger.info("%d locations due for polling", len(due_locations))
                # Split locations into batches of 10
                batches = [
                    due_locations[i:i + _BATCH_SIZE]
                    for i in range(0, len(due_locations), _BATCH_SIZE)
                ]
                
                logger.info(
                    "Polling %d locations in %d batch(es) of up to %d locations each",
                    len(due_locations),
                    len(batches),
                    _BATCH_SIZE,
                )
                
                # Process each batch
                hit_backoff = False
                for batch_num, batch in enumerate(batches, 1):
                    if await self._check_backoff():
                        logger.warning("Open-Meteo API entered backoff. Stopping remaining %d batches.", len(batches) - batch_num + 1)
                        hit_backoff = True
                        break
                        
                    try:
                        logger.debug(
                            "Processing batch %d/%d with %d locations",
                            batch_num,
                            len(batches),
                            len(batch),
                        )
                        
                        # Collect batch data (single API call)
                        batch_stats = await self.collect_batch(batch, cycle_id=cycle_id)
                        
                        # Update counters
                        self.locations_success += batch_stats["locations_success"]
                        self.locations_failed += batch_stats["locations_failed"]
                        total_hourly += batch_stats["total_hourly"]
                        total_daily += batch_stats["total_daily"]
                        total_breaches += batch_stats["total_breaches"]
                        error_summary.update(batch_stats["errors"])
                        if batch_stats.get("latency_ms", 0) > 0:
                            total_latency += batch_stats["latency_ms"]
                            api_calls_made += 1
                        
                        # Rate limit delay between batches (500ms)
                        if batch_num < len(batches):
                            await self.rate_limit_delay(settings.openmeteo_request_delay_ms)
                        
                    except Exception as e:
                        logger.error("Failed to process batch %d: %s", batch_num, str(e))
                        # Mark all locations in batch as failed
                        self.locations_failed += len(batch)
                        continue
                
                # Determine cycle status
                if self.locations_failed > 0 or hit_backoff:
                    if self.locations_success > 0:
                        cycle_status = "partial"
                    elif hit_backoff:
                        cycle_status = "skipped"
                    else:
                        cycle_status = "failed"
            
        except Exception as e:
            logger.error("Unexpected error during Open-Meteo collection: %s", str(e))
            cycle_status = "failed"
            error_message = str(e)
        
        finally:
            avg_latency = total_latency / api_calls_made if api_calls_made > 0 else None
            
            # Complete cycle tracking
            await self.cycle_repo.complete_cycle(
                cycle_id=cycle_id,
                status=cycle_status,
                locations_targeted=self.locations_targeted,
                locations_success=self.locations_success,
                locations_failed=self.locations_failed,
                rows_upserted=total_hourly + total_daily,
                rows_inserted=total_hourly + total_daily,
                breaches_triggered=total_breaches,
                rate_limit_hits=self.rate_limit_hits,
                failure_reason=error_message,
                error_summary=error_summary if error_summary else None,
                avg_latency_ms=avg_latency,
            )
            
            cycle_duration_ms = int((datetime.now(_PKT) - cycle_start_time).total_seconds() * 1000)
            logger.info(
                "Weather cycle complete: %d/%d locations, %d rows, %d breaches [%dms]",
                self.locations_success,
                self.locations_targeted,
                total_hourly + total_daily,
                total_breaches,
                cycle_duration_ms,
            )
        
        return {
            "cycle_id": cycle_id,
            "status": cycle_status,
            "locations_targeted": self.locations_targeted,
            "locations_success": self.locations_success,
            "locations_failed": self.locations_failed,
            "hourly_rows": total_hourly,
            "daily_rows": total_daily,
            "breaches_detected": total_breaches,
            "error": error_message,
        }
