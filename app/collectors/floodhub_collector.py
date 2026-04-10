"""
ClimaSync Collection Service — Google Flood Hub Collector

Polls Google Flood Hub API for flood gauge readings and forecasts.

Key responsibilities:
  - Fetch current water levels for all active gauges
  - Fetch probabilistic forecasts (p10/p50/p90)
  - Track cycle metrics per gauge
  - Handle Google Cloud API authentication
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
from app.models.flood_models import FloodGaugeRegistry
from app.repositories.cycle_repository import CycleRepository
from app.repositories.reference_repository import ReferenceRepository
from app.repositories.flood_repository import FloodRepository
from app.services.floodhub_service import FloodHubService

logger = get_logger(__name__)
settings = get_settings()

# Pakistan Standard Time
_PKT = ZoneInfo("Asia/Karachi")


class FloodHubCollector(BaseCollector):
    """Collects flood gauge data from Google Flood Hub API.
    
    Inherits HTTP client, retry logic, and rate limit handling from BaseCollector.
    """

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        reference_repo: ReferenceRepository,
        cycle_repo: CycleRepository,
        flood_repo: FloodRepository,
        floodhub_service: FloodHubService,
        flood_gauges: list[FloodGaugeRegistry],
    ) -> None:
        """Initialize Flood Hub collector.
        
        Args:
            http_client: Shared async HTTP client.
            reference_repo: Repository for API config and backoff.
            cycle_repo: Repository for cycle tracking.
            flood_repo: Repository for flood data.
            floodhub_service: Service for parsing and processing flood data.
            flood_gauges: List of all active flood gauges.
        """
        super().__init__(
            api_name="google_flood_hub",
            http_client=http_client,
            reference_repo=reference_repo,
        )
        
        self.cycle_repo = cycle_repo
        self.flood_repo = flood_repo
        self.floodhub_service = floodhub_service
        self.flood_gauges = flood_gauges
        
        logger.info("FloodHubCollector initialized with %d gauges", len(flood_gauges))

    # ── Current Reading Collection ────────────────────────────────

    async def collect_current_reading(
        self,
        gauge: FloodGaugeRegistry,
    ) -> dict[str, Any]:
        """Collect current water level for a single gauge.
        
        Args:
            gauge: Flood gauge to collect data for.
        
        Returns:
            Dictionary with collection statistics.
        """
        stats = {
            "gauge_name": gauge.gauge_name,
            "success": False,
            "breach_detected": False,
            "error": None,
        }
        
        try:
            # Build API URL
            url = f"{settings.google_flood_hub_base_url}/gauges/{gauge.google_gauge_id}/current"
            
            # Add API key to headers
            headers = {
                "Authorization": f"Bearer {settings.google_flood_hub_api_key}",
            }
            
            # Fetch current reading
            response = await self.get(url=url, params={})
            
            # Note: Google Flood Hub API requires custom headers
            # We need to override the get method or pass headers
            # For now, we'll use a direct httpx call
            response = await self.http_client.get(url, headers=headers)
            
            if response.status_code != 200:
                raise ApiResponseError("google_flood_hub", response.status_code, response.text)
            
            data = response.json()
            
            # Get previous reading from database (if exists)
            previous_reading = await self.flood_repo.get_previous_reading(str(gauge.gauge_id))
            
            # Parse current reading
            current = await self.floodhub_service.parse_current_reading(
                response=data,
                gauge=gauge,
                previous_reading=previous_reading,
            )
            
            # Process reading (check breach, UPSERT)
            process_stats = await self.floodhub_service.process_current_reading(current)
            
            stats["success"] = process_stats["success"]
            stats["breach_detected"] = process_stats["breach_detected"]
            
            logger.debug(
                "Collected current reading for %s: level=%.2fm",
                gauge.gauge_name,
                current.current_level_m,
            )
            
        except ApiResponseError as e:
            logger.error("API error for %s: %s", gauge.gauge_name, str(e))
            stats["error"] = str(e)
            
        except Exception as e:
            logger.error("Unexpected error for %s: %s", gauge.gauge_name, str(e))
            stats["error"] = str(e)
        
        return stats

    async def collect_current_readings(self) -> dict[str, Any]:
        """Execute one current readings collection cycle.
        
        Polls all active gauges for current water levels.
        
        Returns:
            Dictionary with cycle statistics.
        """
        # Load API config to get api_id
        api_config = await self._load_api_config()
        
        # Start cycle tracking
        cycle_id = await self.cycle_repo.start_cycle(str(api_config.api_id), self.api_name)
        
        logger.info("Starting Flood Hub current readings cycle: %s", cycle_id)
        
        # Reset counters
        self.reset_counters()
        
        cycle_status = "completed"
        total_breaches = 0
        error_message = None
        
        try:
            self.locations_targeted = len(self.flood_gauges)
            
            if not self.flood_gauges:
                logger.info("No flood gauges to poll")
                cycle_status = "skipped"
            else:
                # Collect data for each gauge
                for gauge in self.flood_gauges:
                    try:
                        gauge_stats = await self.collect_current_reading(gauge)
                        
                        if gauge_stats["success"]:
                            self.increment_success()
                            if gauge_stats["breach_detected"]:
                                total_breaches += 1
                        else:
                            self.increment_failure()
                        
                    except Exception as e:
                        logger.error("Failed to collect gauge %s: %s", gauge.gauge_name, str(e))
                        self.increment_failure()
                        continue
                
                # Determine cycle status
                if self.locations_failed > 0:
                    if self.locations_success > 0:
                        cycle_status = "partial"
                    else:
                        cycle_status = "failed"
            
        except Exception as e:
            logger.error("Unexpected error during Flood Hub current readings: %s", str(e))
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
                rows_upserted=self.locations_success,  # 1 row per gauge
                rows_inserted=self.locations_success,
                breaches_triggered=total_breaches,
                rate_limit_hits=self.rate_limit_hits,
            )
            
            logger.info(
                "Flood Hub current readings cycle %s completed: status=%s, gauges=%d/%d, breaches=%d",
                cycle_id,
                cycle_status,
                self.locations_success,
                self.locations_targeted,
                total_breaches,
            )
        
        return {
            "cycle_id": cycle_id,
            "status": cycle_status,
            "gauges_targeted": self.locations_targeted,
            "gauges_success": self.locations_success,
            "gauges_failed": self.locations_failed,
            "breaches_detected": total_breaches,
            "error": error_message,
        }

    # ── Forecast Collection ───────────────────────────────────────

    async def collect_forecast(
        self,
        gauge: FloodGaugeRegistry,
    ) -> dict[str, Any]:
        """Collect probabilistic forecasts for a single gauge.
        
        Args:
            gauge: Flood gauge to collect forecasts for.
        
        Returns:
            Dictionary with collection statistics.
        """
        stats = {
            "gauge_name": gauge.gauge_name,
            "success": False,
            "forecasts_count": 0,
            "breaches_detected": 0,
            "error": None,
        }
        
        try:
            # Build API URL
            url = f"{settings.google_flood_hub_base_url}/gauges/{gauge.google_gauge_id}/forecasts"
            
            # Add API key to headers
            headers = {
                "Authorization": f"Bearer {settings.google_flood_hub_api_key}",
            }
            
            # Fetch forecasts
            response = await self.http_client.get(url, headers=headers)
            
            if response.status_code != 200:
                raise ApiResponseError("google_flood_hub", response.status_code, response.text)
            
            data = response.json()
            
            # Parse forecasts
            forecasts = self.floodhub_service.parse_forecast(
                response=data,
                gauge=gauge,
            )
            
            # Process forecasts (check breaches, UPSERT)
            process_stats = await self.floodhub_service.process_forecasts(forecasts, gauge)
            
            stats["success"] = True
            stats["forecasts_count"] = process_stats["forecasts_processed"]
            stats["breaches_detected"] = process_stats["breaches_detected"]
            
            logger.debug(
                "Collected %d forecasts for %s",
                stats["forecasts_count"],
                gauge.gauge_name,
            )
            
        except ApiResponseError as e:
            logger.error("API error for %s forecasts: %s", gauge.gauge_name, str(e))
            stats["error"] = str(e)
            
        except Exception as e:
            logger.error("Unexpected error for %s forecasts: %s", gauge.gauge_name, str(e))
            stats["error"] = str(e)
        
        return stats

    async def collect_forecasts(self) -> dict[str, Any]:
        """Execute one forecast collection cycle.
        
        Polls all active gauges for probabilistic forecasts.
        
        Returns:
            Dictionary with cycle statistics.
        """
        # Load API config to get api_id
        api_config = await self._load_api_config()
        
        # Start cycle tracking
        cycle_id = await self.cycle_repo.start_cycle(str(api_config.api_id), self.api_name)
        
        logger.info("Starting Flood Hub forecasts cycle: %s", cycle_id)
        
        # Reset counters
        self.reset_counters()
        
        cycle_status = "completed"
        total_forecasts = 0
        total_breaches = 0
        error_message = None
        
        try:
            self.locations_targeted = len(self.flood_gauges)
            
            if not self.flood_gauges:
                logger.info("No flood gauges to poll")
                cycle_status = "skipped"
            else:
                # Collect forecasts for each gauge
                for gauge in self.flood_gauges:
                    try:
                        gauge_stats = await self.collect_forecast(gauge)
                        
                        if gauge_stats["success"]:
                            self.increment_success()
                            total_forecasts += gauge_stats["forecasts_count"]
                            total_breaches += gauge_stats["breaches_detected"]
                        else:
                            self.increment_failure()
                        
                    except Exception as e:
                        logger.error("Failed to collect forecasts for %s: %s", gauge.gauge_name, str(e))
                        self.increment_failure()
                        continue
                
                # Determine cycle status
                if self.locations_failed > 0:
                    if self.locations_success > 0:
                        cycle_status = "partial"
                    else:
                        cycle_status = "failed"
            
        except Exception as e:
            logger.error("Unexpected error during Flood Hub forecasts: %s", str(e))
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
                rows_upserted=total_forecasts,
                rows_inserted=total_forecasts,
                breaches_triggered=total_breaches,
                rate_limit_hits=self.rate_limit_hits,
            )
            
            logger.info(
                "Flood Hub forecasts cycle %s completed: status=%s, gauges=%d/%d, forecasts=%d, breaches=%d",
                cycle_id,
                cycle_status,
                self.locations_success,
                self.locations_targeted,
                total_forecasts,
                total_breaches,
            )
        
        return {
            "cycle_id": cycle_id,
            "status": cycle_status,
            "gauges_targeted": self.locations_targeted,
            "gauges_success": self.locations_success,
            "gauges_failed": self.locations_failed,
            "forecasts_count": total_forecasts,
            "breaches_detected": total_breaches,
            "error": error_message,
        }
