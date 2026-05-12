"""
ClimaSync Collection Service — Dispatch Service

Sends threshold breach alerts to the main ClimaSync system.

Key responsibilities:
  - Fetch pending breaches from database
  - Build dispatch payload with all required fields
  - POST to main system API with authentication
  - Mark breaches as dispatched or failed
  - Retry failed dispatches up to max attempts
  - Stop retrying after 5 failed attempts (requires manual intervention)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.core.config import get_settings
from app.core.logger import get_logger
from app.repositories.breach_repository import BreachRepository

logger = get_logger(__name__)
settings = get_settings()

# Pakistan Standard Time
_PKT = ZoneInfo("Asia/Karachi")


class DispatchService:
    """Dispatches threshold breach alerts to the main ClimaSync system.
    
    Manages the lifecycle of breach dispatch: fetch pending, send to main system,
    mark as dispatched or failed, retry on failure.
    """

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        breach_repo: BreachRepository,
    ) -> None:
        """Initialize Dispatch service.
        
        Args:
            http_client: Shared async HTTP client.
            breach_repo: Repository for breach data.
        """
        self.http_client = http_client
        self.breach_repo = breach_repo
        
        logger.info("DispatchService initialized")

    # ── Payload Building ──────────────────────────────────────────

    def build_dispatch_payload(self, breach: dict[str, Any]) -> dict[str, Any]:
        """Build dispatch payload from breach data.
        
        Args:
            breach: Breach dictionary from database.
        
        Returns:
            Dispatch payload ready for POST to main system.
        """
        # Extract and format fields
        breach_id = str(breach["breach_id"])
        source_api = breach["source_api"]
        disaster_kind = breach["disaster_kind"]
        metric_name = breach["metric_name"]
        location_name = breach.get("location_name")
        district = breach.get("district")
        province = breach.get("province")
        latitude = breach.get("latitude")
        longitude = breach.get("longitude")
        observed_value = breach["observed_value"]
        threshold_value = breach["threshold_value"]
        breach_severity = breach["breach_severity"]
        observation_time = breach["observation_time"]
        is_forecast = breach.get("is_forecast_breach", False)
        forecast_horizon_h = breach.get("forecast_horizon_h")
        detected_at = breach["detected_at"]
        
        # Format timestamps as ISO strings
        observation_time_str = observation_time.isoformat() if isinstance(observation_time, datetime) else observation_time
        detected_at_str = detected_at.isoformat() if isinstance(detected_at, datetime) else detected_at
        
        # Build payload
        payload = {
            "breach_id": breach_id,
            "source_api": source_api,
            "disaster_kind": disaster_kind,
            "metric_name": metric_name,
            "location_name": location_name,
            "district": district,
            "province": province,
            "latitude": latitude,
            "longitude": longitude,
            "observed_value": observed_value,
            "threshold_value": threshold_value,
            "breach_severity": breach_severity,
            "unit": self._get_metric_unit(metric_name),
            "observation_time": observation_time_str,
            "is_forecast": is_forecast,
            "forecast_horizon_h": forecast_horizon_h,
            "detected_at": detected_at_str,
        }
        
        return payload

    def _get_metric_unit(self, metric_name: str) -> str:
        """Get unit for a metric name.
        
        Args:
            metric_name: Metric name.
        
        Returns:
            Unit string.
        """
        # Map metric names to units
        unit_map = {
            "magnitude": "richter",
            "temp_max_c": "celsius",
            "temp_min_c": "celsius",
            "temp_c": "celsius",
            "precip_mm": "mm",
            "precip_24h_mm": "mm",
            "wind_speed_kmh": "km/h",
            "wind_gusts_kmh": "km/h",
            "pct_of_danger": "percent",
            "pct_of_warning": "percent",
            "current_level_m": "meters",
        }
        
        return unit_map.get(metric_name, "unknown")

    # ── Dispatch Execution ────────────────────────────────────────

    async def dispatch_breach(self, breach: dict[str, Any]) -> tuple[bool, str | None, str | None]:
        """Dispatch a single breach to the main system.
        
        Args:
            breach: Breach dictionary from database.
        
        Returns:
            Tuple of (success, alert_id_or_error_message, error_message).
            If success is True, the second element is the alert_id (or None), and the third is None.
            If success is False, the second element is None, and the third is the error message.
        """
        breach_id = str(breach["breach_id"])
        
        try:
            # Build payload
            payload = self.build_dispatch_payload(breach)
            
            # Build URL
            url = f"{settings.main_system_base_url}/alerts/incoming"
            
            # Build headers
            headers = {
                "X-API-Key": settings.main_system_api_key,
                "Content-Type": "application/json",
            }
            
            # POST to main system
            response = await self.http_client.post(
                url,
                json=payload,
                headers=headers,
                timeout=30.0,
            )
            
            # Check response
            if response.status_code in (200, 201):
                logger.info(
                    "Successfully dispatched breach %s: %s %s at %s",
                    breach_id,
                    breach["disaster_kind"],
                    breach["breach_severity"],
                    breach.get("location_name", "unknown"),
                )
                try:
                    resp_json = response.json()
                    alert_id = resp_json.get("alert_id") or resp_json.get("id")
                except Exception:
                    alert_id = None
                return True, alert_id, None
            else:
                error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                logger.warning("Failed to dispatch breach %s: %s", breach_id, error_msg)
                return False, None, error_msg
            
        except httpx.TimeoutException as e:
            error_msg = f"Timeout: {str(e)}"
            logger.warning("Timeout dispatching breach %s: %s", breach_id, error_msg)
            return False, None, error_msg
            
        except httpx.ConnectError as e:
            error_msg = f"Connection error: {str(e)}"
            logger.warning("Connection error dispatching breach %s: %s", breach_id, error_msg)
            return False, None, error_msg
            
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error("Unexpected error dispatching breach %s: %s", breach_id, error_msg)
            return False, None, error_msg

    # ── Batch Dispatch ────────────────────────────────────────────

    async def run_dispatch_batch(self) -> dict[str, Any]:
        """Execute one dispatch batch cycle.
        
        Fetches pending breaches and dispatches them to the main system.
        
        Returns:
            Dictionary with dispatch statistics.
        """
        logger.debug("Starting dispatch batch")
        
        stats = {
            "breaches_targeted": 0,
            "breaches_dispatched": 0,
            "breaches_failed": 0,
            "breaches_max_attempts": 0,
        }
        
        try:
            # Fetch undispatched breaches
            breaches = await self.breach_repo.get_undispatched_breaches(
                max_attempts=settings.max_dispatch_attempts,
                batch_size=settings.dispatch_batch_size,
            )
            
            stats["breaches_targeted"] = len(breaches)
            
            if not breaches:
                logger.debug("No pending breaches to dispatch")
                return stats
            
            logger.info("Dispatching %d pending breaches", len(breaches))
            
            # Dispatch each breach
            for breach in breaches:
                breach_id = str(breach["breach_id"])
                attempt_count = breach["dispatch_attempt_count"]
                
                # Check if max attempts reached
                if attempt_count >= settings.max_dispatch_attempts:
                    logger.warning(
                        "Breach %s has reached max attempts (%d), skipping",
                        breach_id,
                        settings.max_dispatch_attempts,
                    )
                    stats["breaches_max_attempts"] += 1
                    continue
                
                # Dispatch breach
                success, alert_id, error_msg = await self.dispatch_breach(breach)
                
                if success:
                    # Mark as dispatched
                    await self.breach_repo.mark_dispatched(breach_id, main_system_alert_id=alert_id)
                    stats["breaches_dispatched"] += 1
                else:
                    # Mark as failed
                    await self.breach_repo.mark_dispatch_failed(breach_id, error_msg or "Unknown error")
                    stats["breaches_failed"] += 1
                    
                    # Check if this was the last attempt
                    if attempt_count + 1 >= settings.max_dispatch_attempts:
                        logger.error(
                            "Breach %s has failed %d times, manual intervention required",
                            breach_id,
                            settings.max_dispatch_attempts,
                        )
            
            logger.info(
                "Dispatch batch complete: %d dispatched, %d failed, %d max attempts",
                stats["breaches_dispatched"],
                stats["breaches_failed"],
                stats["breaches_max_attempts"],
            )
            
        except Exception as e:
            logger.error("Unexpected error during dispatch batch: %s", str(e))
        
        return stats
