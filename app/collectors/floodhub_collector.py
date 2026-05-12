"""
ClimaSync Collection Service — Google Flood Hub Collector

Polls the Google Flood Forecasting API for river gauge data.
Two separate collection methods:
  - collect_current(): Current gauge readings (every 60 minutes)
  - collect_forecast(): Probabilistic forecasts (every 6 hours)

Both share the SAME api_registry entry for google_flood_hub.
"""

import asyncio
import logging
import time
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import Settings, get_settings
from app.core.exceptions import ApiRateLimitError, ApiResponseError, APIUnavailableError
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

    Uses individual /gauges/{id} and /gauges/{id}/forecasts endpoints.
    Exposes two separate collection methods for the scheduler.
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

    # ── HTTP Fetch Methods ─────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
        reraise=True,
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )
    async def _fetch_current_reading(self, google_gauge_id: str) -> dict | None:
        """Fetch current reading for a specific gauge."""
        url = f"{self.settings.google_flood_hub_base_url}/gauges/{google_gauge_id}"
        logger.debug("Calling %s [auth=api_key]", url)

        headers = {
            "User-Agent": "ClimaSync.ai/1.0 Pakistan Disaster Monitor",
            "Accept": "application/json"
        }
        params = {"key": self.settings.google_flood_hub_api_key}

        try:
            response = await self.http_client.get(
                url,
                params=params,
                headers=headers,
                timeout=httpx.Timeout(30.0, connect=10.0)
            )

            if response.status_code == 404:
                logger.debug("No data available for gauge %s (404)", google_gauge_id)
                return None
            elif response.status_code == 403:
                logger.critical("CRITICAL: Invalid API Key for Google Flood Hub (403).")
                raise APIUnavailableError("google_flood_hub", "Invalid API Key (HTTP 403)")
            elif response.status_code == 429:
                await self._handle_rate_limit(response)
            elif 500 <= response.status_code < 600:
                raise httpx.ConnectError(f"Server error {response.status_code}")

            response.raise_for_status()

            data = response.json()
            if data.get('latestReading') is None:
                logger.debug("No data available for gauge %s (404)", google_gauge_id)
                return None

            return data

        except httpx.HTTPStatusError as e:
            if 500 <= e.response.status_code < 600:
                raise httpx.ConnectError(f"Server Error {e.response.status_code}") from e
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
        reraise=True,
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )
    async def _fetch_forecast(self, google_gauge_id: str) -> dict | None:
        """Fetch forecasts for a specific gauge."""
        url = f"{self.settings.google_flood_hub_base_url}/gauges/{google_gauge_id}/forecasts"
        logger.debug("Calling %s [auth=api_key]", url)

        headers = {
            "User-Agent": "ClimaSync.ai/1.0 Pakistan Disaster Monitor",
            "Accept": "application/json"
        }
        params = {"key": self.settings.google_flood_hub_api_key}

        try:
            response = await self.http_client.get(
                url,
                params=params,
                headers=headers,
                timeout=httpx.Timeout(30.0, connect=10.0)
            )

            if response.status_code == 404:
                logger.warning("No forecast data for %s", google_gauge_id)
                return None
            elif response.status_code == 403:
                logger.critical("CRITICAL: Invalid API Key for Google Flood Hub (403).")
                raise APIUnavailableError("google_flood_hub", "Invalid API Key (HTTP 403)")
            elif response.status_code == 429:
                await self._handle_rate_limit(response)
            elif 500 <= response.status_code < 600:
                raise httpx.ConnectError(f"Server error {response.status_code}")

            response.raise_for_status()

            data = response.json()
            forecasts_list = data.get('forecasts')
            if forecasts_list is None or not isinstance(forecasts_list, list) or len(forecasts_list) == 0:
                logger.warning("No forecast data for %s", google_gauge_id)
                return None

            return data

        except httpx.HTTPStatusError as e:
            if 500 <= e.response.status_code < 600:
                raise httpx.ConnectError(f"Server Error {e.response.status_code}") from e
            raise

    # ── Job 1: Current Reading Collection (every 60 min) ───────────

    async def collect_current(self) -> dict:
        """Execute flood current reading collection, gauge by gauge.

        K4: If no active gauges, log WARNING and return without cycle.
        L1: Backoff is checked before EACH gauge, not just at cycle start.
        """
        # K4. Empty active gauges
        if not self.flood_gauges:
            logger.warning("No active flood gauges found — skipping flood_current cycle")
            return {"status": "skipped", "reason": "no_gauges"}

        api_config = await self._load_api_config()

        # L1/L4. Check persisted backoff before starting cycle
        if await self._check_backoff():
            cycle_id = await self.cycle_repo.start_cycle(
                str(api_config.api_id), "google_flood_hub", "flood_current"
            )
            await self.cycle_repo.complete_cycle(
                cycle_id=cycle_id,
                status="skipped",
                failure_reason="API in backoff period",
                locations_targeted=len(self.flood_gauges),
            )
            return {"status": "skipped", "reason": "backoff"}

        cycle_id = await self.cycle_repo.start_cycle(
            str(api_config.api_id), "google_flood_hub", "flood_current"
        )
        logger.info("Flood current cycle starting [cycle_id=%s]", cycle_id)
        logger.info("%d active flood gauges to process", len(self.flood_gauges))

        stats = {
            "locations_targeted": len(self.flood_gauges),
            "locations_success": 0,
            "locations_failed": 0,
            "locations_skipped": 0,
            "rows_upserted": 0,
            "breaches_triggered": 0,
            "total_api_calls": 0,
            "latency_sum_ms": 0.0,
        }
        rate_limited = False

        try:
            for gauge in self.flood_gauges:
                # L1. Check backoff before EACH gauge
                if await self._check_backoff():
                    remaining = len(self.flood_gauges) - (
                        stats["locations_success"] + stats["locations_failed"] + stats["locations_skipped"]
                    )
                    stats["locations_skipped"] += remaining
                    rate_limited = True
                    logger.warning("Rate limit hit mid-cycle at gauge %s, skipping %d remaining", gauge.google_gauge_id, remaining)
                    break

                try:
                    logger.debug("Fetching current reading for %s (%s)", gauge.gauge_name, gauge.google_gauge_id)
                    t0 = time.monotonic()
                    current_data = await self._fetch_current_reading(gauge.google_gauge_id)
                    stats["total_api_calls"] += 1
                    stats["latency_sum_ms"] += (time.monotonic() - t0) * 1000

                    if current_data is None:
                        # 404 or missing latestReading — not a failure
                        stats["locations_skipped"] += 1
                        continue

                    previous_reading = await self.flood_repo.get_previous_reading(str(gauge.gauge_id))
                    current_obj = await self.floodhub_service.parse_current_data(
                        data=current_data,
                        gauge=gauge,
                        previous_reading=previous_reading
                    )
                    if current_obj:
                        res = await self.floodhub_service.process_current_reading(current_obj, gauge)
                        if res["success"]:
                            logger.info("Wrote current reading for %s", gauge.google_gauge_id)
                            stats["locations_success"] += 1
                            stats["rows_upserted"] += 1
                            if res.get("breach_detected"):
                                stats["breaches_triggered"] += 1
                        else:
                            stats["locations_failed"] += 1
                    else:
                        stats["locations_skipped"] += 1

                except APIUnavailableError:
                    raise  # Bubble up 403 immediately
                except ApiRateLimitError:
                    # L1. Rate limit mid-cycle — abort remaining
                    remaining = len(self.flood_gauges) - (
                        stats["locations_success"] + stats["locations_failed"] + stats["locations_skipped"]
                    )
                    stats["locations_skipped"] += remaining
                    rate_limited = True
                    break
                except Exception as e:
                    logger.error("Error processing gauge %s: %s", gauge.gauge_name, e, exc_info=True)
                    stats["locations_failed"] += 1

                # 500ms delay between gauges
                await asyncio.sleep(self.settings.openmeteo_request_delay_ms / 1000.0)

            # K5. Determine cycle status
            if rate_limited:
                status = "partial" if stats["locations_success"] > 0 else "skipped"
            elif stats["locations_failed"] == 0:
                status = "completed"
            elif stats["locations_success"] > 0:
                status = "partial"
            else:
                status = "failed"

            avg_latency = (
                stats["latency_sum_ms"] / stats["total_api_calls"]
                if stats["total_api_calls"] > 0 else None
            )

            await self.cycle_repo.complete_cycle(
                cycle_id=cycle_id,
                status=status,
                locations_targeted=stats["locations_targeted"],
                locations_success=stats["locations_success"],
                locations_failed=stats["locations_failed"],
                rows_upserted=stats["rows_upserted"],
                breaches_triggered=stats["breaches_triggered"],
                rate_limit_hits=1 if rate_limited else 0,
                avg_latency_ms=avg_latency,
            )
            logger.info(
                "Flood current complete: %d/%d gauges, %d breaches [%dms]",
                stats["locations_success"], stats["locations_targeted"],
                stats["breaches_triggered"], int(stats["latency_sum_ms"])
            )
            return stats

        except APIUnavailableError as e:
            logger.critical("Google Flood Hub API key invalid. Flood collection disabled.")
            await self.cycle_repo.complete_cycle(
                cycle_id=cycle_id,
                status="failed",
                failure_reason=str(e),
                locations_targeted=stats["locations_targeted"],
            )
            return {"status": "failed", "error": str(e)}
        except Exception as e:
            logger.error(f"Flood current collection failed: {e}", exc_info=True)
            await self.cycle_repo.complete_cycle(
                cycle_id=cycle_id,
                status="failed",
                failure_reason=str(e),
                locations_targeted=stats["locations_targeted"],
                locations_failed=stats["locations_targeted"],
            )
            return {"status": "failed", "error": str(e)}

    # ── Job 2: Forecast Collection (every 6 hours) ─────────────────

    async def collect_forecast(self) -> dict:
        """Execute flood forecast collection, gauge by gauge.

        K4: If no active gauges, log WARNING and return without cycle.
        L1: Backoff is checked before EACH gauge, not just at cycle start.
        """
        # K4. Empty active gauges
        if not self.flood_gauges:
            logger.warning("No active flood gauges found — skipping flood_forecast cycle")
            return {"status": "skipped", "reason": "no_gauges"}

        api_config = await self._load_api_config()

        # L1/L4. Check persisted backoff before starting cycle
        if await self._check_backoff():
            cycle_id = await self.cycle_repo.start_cycle(
                str(api_config.api_id), "google_flood_hub", "flood_forecast"
            )
            await self.cycle_repo.complete_cycle(
                cycle_id=cycle_id,
                status="skipped",
                failure_reason="API in backoff period",
                locations_targeted=len(self.flood_gauges),
            )
            return {"status": "skipped", "reason": "backoff"}

        cycle_id = await self.cycle_repo.start_cycle(
            str(api_config.api_id), "google_flood_hub", "flood_forecast"
        )
        logger.info("Flood forecast cycle starting [cycle_id=%s]", cycle_id)
        logger.info("%d active flood gauges to process", len(self.flood_gauges))

        stats = {
            "locations_targeted": len(self.flood_gauges),
            "locations_success": 0,
            "locations_failed": 0,
            "locations_skipped": 0,
            "rows_upserted": 0,
            "breaches_triggered": 0,
            "total_api_calls": 0,
            "latency_sum_ms": 0.0,
        }
        rate_limited = False

        try:
            for gauge in self.flood_gauges:
                # L1. Check backoff before EACH gauge
                if await self._check_backoff():
                    remaining = len(self.flood_gauges) - (
                        stats["locations_success"] + stats["locations_failed"] + stats["locations_skipped"]
                    )
                    stats["locations_skipped"] += remaining
                    rate_limited = True
                    logger.warning("Rate limit hit mid-cycle at gauge %s, skipping %d remaining", gauge.google_gauge_id, remaining)
                    break

                try:
                    logger.debug("Fetching forecast for %s", gauge.gauge_name)
                    t0 = time.monotonic()
                    forecast_data = await self._fetch_forecast(gauge.google_gauge_id)
                    stats["total_api_calls"] += 1
                    stats["latency_sum_ms"] += (time.monotonic() - t0) * 1000

                    if forecast_data is None:
                        # 404 or empty forecasts — not a failure
                        stats["locations_skipped"] += 1
                        continue

                    forecasts = await self.floodhub_service.parse_forecast_data(
                        data=forecast_data,
                        gauge=gauge
                    )
                    if forecasts:
                        res = await self.floodhub_service.process_forecasts(forecasts, gauge)
                        if res["success"]:
                            stats["locations_success"] += 1
                            stats["rows_upserted"] += res.get("count", len(forecasts))
                        else:
                            stats["locations_failed"] += 1
                    else:
                        stats["locations_skipped"] += 1

                except APIUnavailableError:
                    raise  # Bubble up 403 immediately
                except ApiRateLimitError:
                    # L1. Rate limit mid-cycle — abort remaining
                    remaining = len(self.flood_gauges) - (
                        stats["locations_success"] + stats["locations_failed"] + stats["locations_skipped"]
                    )
                    stats["locations_skipped"] += remaining
                    rate_limited = True
                    break
                except Exception as e:
                    logger.error("Error processing gauge %s: %s", gauge.gauge_name, e, exc_info=True)
                    stats["locations_failed"] += 1

                # 500ms delay between gauges
                await asyncio.sleep(self.settings.openmeteo_request_delay_ms / 1000.0)

            # K5. Determine cycle status
            if rate_limited:
                status = "partial" if stats["locations_success"] > 0 else "skipped"
            elif stats["locations_failed"] == 0:
                status = "completed"
            elif stats["locations_success"] > 0:
                status = "partial"
            else:
                status = "failed"

            avg_latency = (
                stats["latency_sum_ms"] / stats["total_api_calls"]
                if stats["total_api_calls"] > 0 else None
            )

            await self.cycle_repo.complete_cycle(
                cycle_id=cycle_id,
                status=status,
                locations_targeted=stats["locations_targeted"],
                locations_success=stats["locations_success"],
                locations_failed=stats["locations_failed"],
                rows_upserted=stats["rows_upserted"],
                breaches_triggered=stats["breaches_triggered"],
                rate_limit_hits=1 if rate_limited else 0,
                avg_latency_ms=avg_latency,
            )
            logger.info(
                "Flood forecast complete: %d/%d gauges, %d rows, %d breaches [%dms]",
                stats["locations_success"], stats["locations_targeted"],
                stats["rows_upserted"], stats["breaches_triggered"],
                int(stats["latency_sum_ms"])
            )
            return stats

        except APIUnavailableError as e:
            logger.critical("Google Flood Hub API key invalid. Flood collection disabled.")
            await self.cycle_repo.complete_cycle(
                cycle_id=cycle_id,
                status="failed",
                failure_reason=str(e),
                locations_targeted=stats["locations_targeted"],
            )
            return {"status": "failed", "error": str(e)}
        except Exception as e:
            logger.error(f"Flood forecast collection failed: {e}", exc_info=True)
            await self.cycle_repo.complete_cycle(
                cycle_id=cycle_id,
                status="failed",
                failure_reason=str(e),
                locations_targeted=stats["locations_targeted"],
                locations_failed=stats["locations_targeted"],
            )
            return {"status": "failed", "error": str(e)}

    # ── Legacy combined method (kept for backwards compatibility) ───

    async def collect(self) -> dict:
        """Execute both current + forecast collection.

        Retained for backwards compatibility and manual triggers.
        The scheduler uses collect_current() and collect_forecast() separately.
        """
        results = {}
        results["current"] = await self.collect_current()
        results["forecast"] = await self.collect_forecast()
        return results
