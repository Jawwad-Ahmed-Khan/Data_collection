"""
ClimaSync Collection Service — USGS Earthquake Collector

Polls USGS Earthquake API every 60 seconds for recent seismic events.

Key responsibilities:
  - Build USGS API query with Pakistan bounding box
  - Fetch earthquake data in GeoJSON format
  - Pass to USGSService for parsing and processing
  - Track cycle metrics (events fetched, breaches detected)
  - Handle rate limits and backoff
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.collectors.base_collector import BaseCollector
from app.core.config import get_settings
from app.core.exceptions import ApiResponseError
from app.core.logger import get_logger
from app.repositories.cycle_repository import CycleRepository
from app.repositories.reference_repository import ReferenceRepository
from app.services.usgs_service import USGSService

logger = get_logger(__name__)
settings = get_settings()

# Pakistan Standard Time
_PKT = ZoneInfo("Asia/Karachi")


class USGSCollector(BaseCollector):
    """Collects earthquake data from USGS API.
    
    Inherits HTTP client, retry logic, and rate limit handling from BaseCollector.
    """

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        reference_repo: ReferenceRepository,
        cycle_repo: CycleRepository,
        usgs_service: USGSService,
    ) -> None:
        """Initialize USGS collector.
        
        Args:
            http_client: Shared async HTTP client.
            reference_repo: Repository for API config and backoff.
            cycle_repo: Repository for cycle tracking.
            usgs_service: Service for parsing and processing USGS data.
        """
        super().__init__(
            api_name="usgs",
            http_client=http_client,
            reference_repo=reference_repo,
        )
        
        self.cycle_repo = cycle_repo
        self.usgs_service = usgs_service
        
        logger.info("USGSCollector initialized")

    # ── Query Building ────────────────────────────────────────────

    def _build_query_params(self) -> dict[str, Any]:
        """Build USGS API query parameters.
        
        Returns:
            Dictionary of query parameters.
        """
        # Time window: last 6 hours (to catch USGS revisions)
        now = datetime.now(_PKT)
        start_time = now - timedelta(hours=settings.usgs_lookback_hours)
        
        # Format times as ISO 8601 (USGS expects UTC)
        start_time_utc = start_time.astimezone(datetime.now().astimezone().tzinfo)
        end_time_utc = now.astimezone(datetime.now().astimezone().tzinfo)
        
        # Pakistan bounding box
        min_lat, max_lat, min_lon, max_lon = settings.pakistan_bounding_box
        
        params = {
            "format": "geojson",
            "minmagnitude": settings.usgs_min_magnitude,
            "starttime": start_time_utc.strftime("%Y-%m-%dT%H:%M:%S"),
            "endtime": end_time_utc.strftime("%Y-%m-%dT%H:%M:%S"),
            "minlatitude": min_lat,
            "maxlatitude": max_lat,
            "minlongitude": min_lon,
            "maxlongitude": max_lon,
            "orderby": "time",
        }
        
        logger.debug(
            "USGS query: M%.1f+, %s to %s, bbox=[%.2f,%.2f,%.2f,%.2f]",
            settings.usgs_min_magnitude,
            params["starttime"],
            params["endtime"],
            min_lat,
            max_lat,
            min_lon,
            max_lon,
        )
        
        return params

    # ── Collection Cycle ──────────────────────────────────────────

    async def collect(self) -> dict[str, Any]:
        """Execute one USGS collection cycle.
        
        Returns:
            Dictionary with cycle statistics.
        """
        # Load API config to get api_id
        api_config = await self._load_api_config()
        
        # Start cycle tracking
        cycle_id = await self.cycle_repo.start_cycle(str(api_config.api_id), self.api_name)
        
        logger.info("Starting USGS collection cycle: %s", cycle_id)
        
        # Reset counters
        self.reset_counters()
        
        cycle_status = "completed"
        events_fetched = 0
        events_upserted = 0
        breaches_detected = 0
        error_message = None
        
        try:
            # Build query parameters
            params = self._build_query_params()
            
            # Fetch earthquake data
            response = await self.get(
                url=settings.usgs_base_url,
                params=params,
            )
            
            # Parse JSON response
            geojson = response.json()
            
            # Extract metadata
            metadata = geojson.get("metadata", {})
            events_fetched = metadata.get("count", 0)
            
            logger.info("USGS returned %d earthquake events", events_fetched)
            
            # Parse events
            events = self.usgs_service.parse_usgs_response(geojson)
            
            # Process events (check breaches, UPSERT to database)
            process_stats = await self.usgs_service.process_events(events)
            
            events_upserted = process_stats["events_upserted"]
            breaches_detected = process_stats["breaches_detected"]
            
            # Update counters
            self.locations_targeted = events_fetched
            self.locations_success = events_upserted
            self.locations_failed = process_stats["errors"]
            
            if process_stats["errors"] > 0:
                cycle_status = "partial"
            
        except ApiResponseError as e:
            logger.error("USGS API error: %s", str(e))
            cycle_status = "failed"
            error_message = str(e)
            self.increment_failure()
            
        except Exception as e:
            logger.error("Unexpected error during USGS collection: %s", str(e))
            cycle_status = "failed"
            error_message = str(e)
            self.increment_failure()
        
        finally:
            # Complete cycle tracking
            await self.cycle_repo.complete_cycle(
                cycle_id=cycle_id,
                status=cycle_status,
                locations_targeted=self.locations_targeted,
                locations_success=self.locations_success,
                locations_failed=self.locations_failed,
                rows_upserted=events_upserted,
                rows_inserted=events_upserted,  # Same for UPSERT
                breaches_triggered=breaches_detected,
                rate_limit_hits=self.rate_limit_hits,
            )
            
            logger.info(
                "USGS cycle %s completed: status=%s, fetched=%d, upserted=%d, breaches=%d",
                cycle_id,
                cycle_status,
                events_fetched,
                events_upserted,
                breaches_detected,
            )
        
        return {
            "cycle_id": cycle_id,
            "status": cycle_status,
            "events_fetched": events_fetched,
            "events_upserted": events_upserted,
            "breaches_detected": breaches_detected,
            "error": error_message,
        }
