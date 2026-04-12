"""
ClimaSync Collection Service — Google Flood Hub Collector

Polls the Google Flood Forecasting API for river gauge data.
Transitioned to V1 API Batch endpoints.
"""

import asyncio
from typing import Any
from zoneinfo import ZoneInfo

from app.core.config import Settings, get_settings
from app.core.exceptions import ApiResponseError
from app.core.logger import get_logger
from app.database.connection import DatabasePool
from app.models.flood_models import FloodGaugeRegistry
from app.repositories.cycle_repository import CycleRepository
from app.repositories.flood_repository import FloodRepository
from app.repositories.reference_repository import ReferenceRepository
from app.services.floodhub_service import FloodHubService
from .base_collector import BaseCollector

logger = get_logger(__name__)
_PKT = ZoneInfo("Asia/Karachi")


class FloodHubCollector(BaseCollector):
    """Collector for Google Flood Hub data.
    
    Uses the Flood Forecasting API (v1) to fetch hydrologic forecasts and status.
    """

    def __init__(
        self,
        http_client,
        reference_repo: ReferenceRepository,
        cycle_repo: CycleRepository,
        flood_repo: FloodRepository,
        floodhub_service: FloodHubService,
        flood_gauges: list[FloodGaugeRegistry],
    ) -> None:
        super().__init__(
            api_name="google_flood_hub",
            http_client=http_client,
            reference_repo=reference_repo,
        )
        self.cycle_repo = cycle_repo
        self.flood_repo = flood_repo
        self.floodhub_service = floodhub_service
        self.flood_gauges = flood_gauges
        self.settings = get_settings()

    async def collect_current_readings(self, force: bool = False) -> dict:
        """Fetch latest floor levels for all active gauges.
        
        Using QueryGaugeForecasts to get the most recent point.
        """
        if not self.flood_gauges:
            return {"status": "skipped", "reason": "no_gauges"}

        api_config = await self._load_api_config()
        cycle_id = await self.cycle_repo.start_cycle(str(api_config.api_id), "google_flood_hub")
        stats = {"total": len(self.flood_gauges), "success": 0, "failed": 0, "breaches": 0}

        try:
            gauge_ids = [g.google_gauge_id for g in self.flood_gauges]
            
            # Real API call
            url = f"{self.settings.google_flood_hub_base_url}/gauges:queryGaugeForecasts"
            params = [("gaugeIds", gid) for gid in gauge_ids]
            params.append(("key", self.settings.google_flood_hub_api_key))
            
            response = await self.http_client.get(url, params=params)
            if response.status_code != 200:
                raise ApiResponseError("google_flood_hub", response.status_code, response.text)
            
            # Response structure is {"forecasts": {"gauge_id": {...}}}
            data = response.json()
            forecast_map = data.get("forecasts", {})

            for gauge in self.flood_gauges:
                try:
                    gauge_data = forecast_map.get(gauge.google_gauge_id)
                    if not gauge_data:
                        logger.warning(f"No data for gauge {gauge.google_gauge_id}")
                        stats["failed"] += 1
                        continue

                    previous_reading = await self.flood_repo.get_previous_reading(str(gauge.gauge_id))
                    
                    # 1. Parse current reading from the earliest point in forecast
                    current = await self.floodhub_service.parse_v1_current(
                        data=gauge_data,
                        gauge=gauge,
                        previous_reading=previous_reading
                    )
                    
                    if current:
                        res_curr = await self.floodhub_service.process_current_reading(current)
                        if res_curr["success"]:
                            stats["success"] += 1
                            if res_curr["breach_detected"]:
                                stats["breaches"] += 1
                        else:
                            stats["failed"] += 1
                    
                    # 2. Parse and process all forecast points
                    forecasts = await self.floodhub_service.parse_forecast_data(
                        data=gauge_data,
                        gauge=gauge
                    )
                    if forecasts:
                        res_fc = await self.floodhub_service.process_forecasts(forecasts)
                        if res_fc["success"]:
                            stats["forecast_points"] = stats.get("forecast_points", 0) + len(forecasts)

                except Exception as e:
                    logger.error(f"Error processing {gauge.google_gauge_id}: {e}")
                    stats["failed"] += 1

            await self.cycle_repo.complete_cycle(
                cycle_id=cycle_id, 
                status="completed" if stats["failed"] == 0 else "partial",
                locations_targeted=stats["total"],
                locations_success=stats["success"],
                locations_failed=stats["failed"],
                breaches_triggered=stats["breaches"]
            )
            return stats

        except Exception as e:
            logger.error(f"Flood Hub collection failed: {e}")
            await self.cycle_repo.complete_cycle(
                cycle_id=cycle_id, 
                status="failed",
                locations_targeted=len(self.flood_gauges),
                locations_failed=len(self.flood_gauges)
            )
            return {"status": "failed", "error": str(e)}

    async def collect_forecasts(self, force: bool = False) -> dict:
        """Fetch forecasts for all active gauges."""
        # Since we get forecasts in the same call in V1, we could combine or re-poll.
        # For simplicity, we'll hit it again to keep the cycles separate.
        return await self.collect_current_readings(force)

    async def collect(self) -> dict:
        """Execute both current and forecast collection."""
        res_current = await self.collect_current_readings()
        res_forecast = await self.collect_forecasts()
        return {"current": res_current, "forecast": res_forecast}
