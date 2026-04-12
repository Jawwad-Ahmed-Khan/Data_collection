"""
ClimaSync Collection Service — Open-Meteo Weather Collector

Polls Open-Meteo API for weather forecasts for all Pakistan locations.

Key responsibilities:
  - Check every 15 minutes which locations are due for polling
  - Sort by poll_priority (critical first)
  - Fetch hourly and daily weather data
  - Apply 500ms rate limit delay between location calls
  - Track cycle metrics per location
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
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

    def get_due_locations(self) -> list[PakistanLocation]:
        """Get locations that are due for polling.
        
        Filters locations where next_poll_due_at <= now() or is None.
        Sorts by poll_priority (critical first).
        
        Returns:
            List of locations due for polling, sorted by priority.
        """
        now = datetime.now(_PKT)
        due_locations = []
        
        for location in self.pakistan_locations:
            # Check if location is due for polling
            # Note: In real implementation, next_poll_due_at would be loaded from database
            # For now, we'll poll all active locations
            if location.is_active:
                due_locations.append(location)
        
        # Sort by poll_priority (critical > high > medium > low)
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        
        # Note: poll_priority not in PakistanLocation model, so we'll sort by name for now
        # In full implementation, this would be loaded from database
        due_locations.sort(key=lambda loc: loc.location_name)
        
        logger.info("Found %d locations due for polling", len(due_locations))
        return due_locations

    # ── Location Collection ───────────────────────────────────────

    async def collect_location(
        self,
        location: PakistanLocation,
        cycle_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Collect weather data for a single location.
        
        Args:
            location: Pakistan location to collect data for.
        
        Returns:
            Dictionary with collection statistics.
        """
        stats = {
            "location_name": location.location_name,
            "success": False,
            "hourly_count": 0,
            "daily_count": 0,
            "breaches": 0,
            "error": None,
        }
        
        try:
            # Build query parameters
            hourly_params = self.openmeteo_service.build_hourly_params(
                latitude=location.latitude,
                longitude=location.longitude,
            )
            
            daily_params = self.openmeteo_service.build_daily_params(
                latitude=location.latitude,
                longitude=location.longitude,
            )
            
            # Fetch hourly data
            hourly_response = await self.get(
                url=settings.openmeteo_base_url,
                params=hourly_params,
            )
            hourly_data = hourly_response.json()
            
            # Fetch daily data
            daily_response = await self.get(
                url=settings.openmeteo_base_url,
                params=daily_params,
            )
            daily_data = daily_response.json()
            
            # Parse data
            hourly_records = self.openmeteo_service.parse_hourly(hourly_data, location)
            daily_summaries = self.openmeteo_service.parse_daily(daily_data, location)
            
            # Process data (check breaches, UPSERT to database)
            process_stats = await self.openmeteo_service.process_location(
                hourly_records=hourly_records,
                daily_summaries=daily_summaries,
                cycle_id=cycle_id,
                data_freshness_minutes=30,  # Default threshold
            )
            
            stats["success"] = True
            stats["hourly_count"] = process_stats["hourly_upserted"]
            stats["daily_count"] = process_stats["daily_upserted"]
            stats["breaches"] = process_stats["breaches_detected"]
            
            logger.debug(
                "Collected weather for %s: %d hourly, %d daily, %d breaches",
                location.location_name,
                stats["hourly_count"],
                stats["daily_count"],
                stats["breaches"],
            )
            
        except ApiResponseError as e:
            logger.error("API error for %s: %s", location.location_name, str(e))
            stats["error"] = str(e)
            
        except Exception as e:
            logger.error("Unexpected error for %s: %s", location.location_name, str(e))
            stats["error"] = str(e)
        
        return stats

    # ── Collection Cycle ──────────────────────────────────────────

    async def collect(self) -> dict[str, Any]:
        """Execute one Open-Meteo collection cycle.
        
        Polls all due locations with 500ms delay between calls.
        
        Returns:
            Dictionary with cycle statistics.
        """
        # Load API config to get api_id
        api_config = await self._load_api_config()
        
        # Start cycle tracking
        cycle_id = await self.cycle_repo.start_cycle(str(api_config.api_id), self.api_name)
        
        logger.info("Starting Open-Meteo collection cycle: %s", cycle_id)
        
        # Reset counters
        self.reset_counters()
        
        cycle_status = "completed"
        total_hourly = 0
        total_daily = 0
        total_breaches = 0
        error_message = None
        
        try:
            # Get locations due for polling
            due_locations = self.get_due_locations()
            self.locations_targeted = len(due_locations)
            
            if not due_locations:
                logger.info("No locations due for polling")
                cycle_status = "skipped"
            else:
                # Collect data for each location
                for i, location in enumerate(due_locations):
                    try:
                        # Collect location data
                        location_stats = await self.collect_location(location, cycle_id=cycle_id)
                        
                        if location_stats["success"]:
                            self.increment_success()
                            total_hourly += location_stats["hourly_count"]
                            total_daily += location_stats["daily_count"]
                            total_breaches += location_stats["breaches"]
                        else:
                            self.increment_failure()
                        
                        # Rate limit delay (500ms between locations)
                        if i < len(due_locations) - 1:  # Don't delay after last location
                            await self.rate_limit_delay(settings.openmeteo_request_delay_ms)
                        
                    except Exception as e:
                        logger.error("Failed to collect location %s: %s", location.location_name, str(e))
                        self.increment_failure()
                        continue
                
                # Determine cycle status
                if self.locations_failed > 0:
                    if self.locations_success > 0:
                        cycle_status = "partial"
                    else:
                        cycle_status = "failed"
            
        except Exception as e:
            logger.error("Unexpected error during Open-Meteo collection: %s", str(e))
            cycle_status = "failed"
            error_message = str(e)
        
        finally:
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
            )
            
            logger.info(
                "Open-Meteo cycle %s completed: status=%s, locations=%d/%d, hourly=%d, daily=%d, breaches=%d",
                cycle_id,
                cycle_status,
                self.locations_success,
                self.locations_targeted,
                total_hourly,
                total_daily,
                total_breaches,
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
