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

from datetime import datetime, timedelta, timezone
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
        start_time_utc = start_time.astimezone(timezone.utc)
        end_time_utc = now.astimezone(timezone.utc)
        
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

    async def _safe_start_cycle(self, api_config: Any, cycle_type: str) -> UUID | None:
        """Create cycle record. Returns None if DB fails."""
        try:
            return await self.cycle_repo.start_cycle(
                api_id=str(api_config.api_id),
                api_name=self.api_name,
                cycle_type=cycle_type
            )
        except Exception as e:
            logger.error("Failed to create cycle record: %s", str(e))
            return None

    async def _safe_complete_cycle(
        self,
        cycle_id: UUID | None,
        status: str,
        events_fetched: int = 0,
        events_upserted: int = 0,
        events_inserted: int = 0,
        locations_failed: int = 0,
        breaches_detected: int = 0,
        failure_reason: str | None = None,
        error_summary: dict[str, Any] | None = None,
    ) -> None:
        """Complete cycle record. Never raises."""
        if cycle_id is None:
            return
        try:
            await self.cycle_repo.complete_cycle(
                cycle_id=cycle_id,
                status=status,
                locations_targeted=events_fetched,
                locations_success=events_upserted,
                locations_failed=locations_failed,
                rows_upserted=events_upserted,
                rows_inserted=events_inserted,
                breaches_triggered=breaches_detected,
                rate_limit_hits=self.rate_limit_hits,
                failure_reason=failure_reason,
                error_summary=error_summary,
            )
        except Exception as e:
            logger.error("Failed to complete cycle record %s: %s", cycle_id, str(e))

    # ── Collection Cycle ──────────────────────────────────────────

    async def collect(self) -> dict[str, Any]:
        """Full USGS cycle. Handles all errors internally.
        
        Returns:
            Dictionary with cycle statistics.
        """
        cycle_id = None
        api_config = None
        
        stats = {
            "events_fetched": 0,
            "events_upserted": 0,
            "events_inserted": 0,
            "events_updated": 0,
            "locations_failed": 0,
            "breaches_detected": 0,
            "errors": {},
            "avg_latency_ms": 0,
        }
        
        self.reset_counters()
        start_time_exec = datetime.now(timezone.utc)

        try:
            # ── 1. Get API registry info ─────────────────────────────────────
            try:
                api_config = await self._load_api_config()
            except Exception as e:
                logger.error("Cannot read api_registry for usgs: %s", str(e))
                return {"status": "failed", "error": "No API config"}
            
            # ── 2. Check backoff ─────────────────────────────────────────────
            now = datetime.now(_PKT)
            backoff_until = api_config.backoff_until
            if backoff_until and backoff_until > now:
                remaining = int((backoff_until - now).total_seconds())
                logger.info("USGS in backoff for %ds more. Skipping cycle.", remaining)
                cycle_id = await self._safe_start_cycle(api_config, "skipped")
                await self._safe_complete_cycle(
                    cycle_id=cycle_id, 
                    status="skipped", 
                    failure_reason=f"Backoff for {remaining}s"
                )
                return {"status": "skipped", "error": "In backoff"}
            
            # ── 3. Start cycle ───────────────────────────────────────────────
            cycle_id = await self._safe_start_cycle(api_config, "scheduled")
            logger.info("USGS collection cycle starting [cycle_id=%s]", cycle_id)
            
            # ── 4. Fetch from USGS ───────────────────────────────────────────
            params = self._build_query_params()
            
            try:
                api_start_time = datetime.now(timezone.utc)
                response = await self.get(
                    url=settings.usgs_base_url,
                    params=params,
                )
                latency_ms = int((datetime.now(timezone.utc) - api_start_time).total_seconds() * 1000)
                stats["avg_latency_ms"] = latency_ms
                
                if "application/json" not in response.headers.get("Content-Type", ""):
                    raise ApiResponseError(self.api_name, response.status_code, "Response is not JSON")
                
                geojson = response.json()
                
                if geojson.get("type") != "FeatureCollection":
                    raise ApiResponseError(self.api_name, response.status_code, "Invalid GeoJSON: not a FeatureCollection")
                if "features" not in geojson:
                    raise ApiResponseError(self.api_name, response.status_code, "Invalid GeoJSON: missing features array")
                
                metadata = geojson.get("metadata", {})
                stats["events_fetched"] = metadata.get("count", 0)
                
                logger.info("USGS API returned %d features [latency=%dms]", stats["events_fetched"], latency_ms)
                
                # Extract raw features list directly
                features = geojson.get("features", [])
                
            except ApiRateLimitError as e:
                logger.warning("USGS API rate limit hit, backing off: %s", str(e))
                self.increment_failure()
                await self._safe_complete_cycle(
                    cycle_id, status="skipped", failure_reason="Rate limited"
                )
                return {"status": "skipped", "error": "Rate limited"}
                
            except ApiResponseError as e:
                logger.error("USGS API error: %s", str(e))
                self.increment_failure()
                await self._safe_complete_cycle(
                    cycle_id, status="failed", failure_reason=str(e)
                )
                return {"status": "failed", "error": str(e)}
                
            except Exception as e:
                logger.error("USGS API unavailable after retries: %s", str(e))
                self.increment_failure()
                await self._safe_complete_cycle(
                    cycle_id, status="failed", failure_reason=str(e)
                )
                return {"status": "failed", "error": str(e)}

            # ── 5. Process each feature ──────────────────────────────────────
            # We map directly to process_events to handle the core logic cleanly
            if features:
                # parse_usgs_response is fully updated to handle parsing and processing
                parsed_events = await self.usgs_service.parse_usgs_response({"features": features})
                process_stats = await self.usgs_service.process_events(parsed_events, cycle_id=cycle_id)
                
                stats["events_upserted"] = process_stats["events_upserted"]
                stats["events_inserted"] = process_stats.get("events_inserted", 0)
                stats["events_updated"] = process_stats.get("events_updated", 0)
                stats["breaches_detected"] = process_stats["breaches_detected"]
                stats["errors"] = process_stats.get("error_details", {})
                stats["locations_failed"] = process_stats["errors"]
            
            # ── 6. Determine final status ────────────────────────────────────
            final_status = "completed"
            failure_reason = None
            
            if stats["locations_failed"] > 0:
                if stats["events_upserted"] == 0 and stats["events_fetched"] > 0:
                    final_status = "failed"
                    failure_reason = "All features failed processing"
                else:
                    final_status = "partial"
                    failure_reason = f"{stats['locations_failed']} features failed processing"
            
            await self._safe_complete_cycle(
                cycle_id=cycle_id,
                status=final_status,
                events_fetched=stats["events_fetched"],
                events_upserted=stats["events_upserted"],
                events_inserted=stats["events_inserted"],
                locations_failed=stats["locations_failed"],
                breaches_detected=stats["breaches_detected"],
                failure_reason=failure_reason,
                error_summary=stats["errors"] if stats["errors"] else None,
            )
            
            duration_ms = int((datetime.now(timezone.utc) - start_time_exec).total_seconds() * 1000)
            logger.info(
                "USGS cycle complete: %d new, %d updated, %d breaches [duration=%dms]",
                stats["events_inserted"],
                stats["events_updated"],
                stats["breaches_detected"],
                duration_ms,
            )
            
            return {
                "cycle_id": str(cycle_id) if cycle_id else None,
                "status": final_status,
                "events_fetched": stats["events_fetched"],
                "events_upserted": stats["events_upserted"],
                "breaches_detected": stats["breaches_detected"],
                "error": failure_reason,
            }

        except Exception as e:
            # Catch-all: something unexpected happened outside normal error paths
            logger.error("USGS cycle unexpected error: %s", str(e), exc_info=True)
            if cycle_id:
                await self._safe_complete_cycle(
                    cycle_id=cycle_id, 
                    status="failed", 
                    failure_reason=f"Unexpected: {str(e)}"
                )
            return {"status": "failed", "error": str(e)}
