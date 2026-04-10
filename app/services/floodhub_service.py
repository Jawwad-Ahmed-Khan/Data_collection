"""
ClimaSync Collection Service — Google Flood Hub Service

Parses Google Flood Hub API responses and processes flood gauge data.

Key responsibilities:
  - Parse current readings and compute derived metrics
  - Parse probabilistic forecasts (p10/p50/p90)
  - Compute river trends and rise rates
  - Estimate time to warning/danger levels
  - Check for threshold breaches
  - UPSERT flood data to database

Note: Google Flood Hub provides water level data in meters.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.core.logger import get_logger
from app.models.flood_models import FloodGaugeCurrentBase, FloodGaugeForecastBase, FloodGaugeRegistry
from app.repositories.flood_repository import FloodRepository
from app.services.breach_service import BreachService

logger = get_logger(__name__)

# Pakistan Standard Time
_PKT = ZoneInfo("Asia/Karachi")


class FloodHubService:
    """Processes Google Flood Hub data.
    
    Parses API responses, computes derived metrics (rise rate, trend, time to thresholds),
    checks breaches, and stores data in database.
    """

    def __init__(
        self,
        flood_repo: FloodRepository,
        breach_service: BreachService,
    ) -> None:
        """Initialize Flood Hub service.
        
        Args:
            flood_repo: Repository for storing flood data.
            breach_service: Service for checking threshold breaches.
        """
        self.flood_repo = flood_repo
        self.breach_service = breach_service
        
        logger.info("FloodHubService initialized")

    # ── Current Reading Parsing ───────────────────────────────────

    async def parse_current_reading(
        self,
        response: dict[str, Any],
        gauge: FloodGaugeRegistry,
        previous_reading: FloodGaugeCurrentBase | None = None,
    ) -> FloodGaugeCurrentBase:
        """Parse current flood gauge reading from Google Flood Hub response.
        
        Args:
            response: Google Flood Hub API response.
            gauge: Flood gauge registry entry.
            previous_reading: Previous reading for computing change rate (optional).
        
        Returns:
            Current flood gauge reading with derived metrics.
        """
        # Extract current level (assuming response has 'waterLevel' in meters)
        current_level_m = response.get("waterLevel", 0.0)
        
        # Extract reading time (ISO format)
        reading_time_str = response.get("timestamp")
        if reading_time_str:
            reading_time = datetime.fromisoformat(reading_time_str.replace("Z", "+00:00")).astimezone(_PKT)
        else:
            reading_time = datetime.now(_PKT)
        
        # Extract threshold levels (if provided by API)
        warning_level_m = response.get("warningLevel")
        danger_level_m = response.get("dangerLevel")
        extreme_level_m = response.get("extremeLevel")
        
        # Compute percentage of thresholds
        pct_of_warning = None
        pct_of_danger = None
        pct_of_historical_max = None
        
        if warning_level_m and warning_level_m > 0:
            pct_of_warning = (current_level_m / warning_level_m) * 100.0
        
        if danger_level_m and danger_level_m > 0:
            pct_of_danger = (current_level_m / danger_level_m) * 100.0
        
        if gauge.historical_max_m and gauge.historical_max_m > 0:
            pct_of_historical_max = (current_level_m / gauge.historical_max_m) * 100.0
        
        # Compute level change and rise rate
        previous_level_m = None
        level_change_m = None
        rise_rate_m_per_hour = None
        river_trend = "stable"
        
        if previous_reading:
            previous_level_m = previous_reading.current_level_m
            level_change_m = current_level_m - previous_level_m
            
            # Compute rise rate (m/hour)
            time_diff = reading_time - previous_reading.reading_time
            hours_diff = time_diff.total_seconds() / 3600.0
            
            if hours_diff > 0:
                rise_rate_m_per_hour = level_change_m / hours_diff
                
                # Classify river trend
                river_trend = self._classify_river_trend(rise_rate_m_per_hour)
        
        # Estimate time to warning/danger
        hours_to_warning = None
        hours_to_danger = None
        
        if rise_rate_m_per_hour and rise_rate_m_per_hour > 0:
            if warning_level_m and current_level_m < warning_level_m:
                hours_to_warning = (warning_level_m - current_level_m) / rise_rate_m_per_hour
            
            if danger_level_m and current_level_m < danger_level_m:
                hours_to_danger = (danger_level_m - current_level_m) / rise_rate_m_per_hour
        
        # Determine flood status
        flood_status = self._determine_flood_status(
            current_level_m,
            warning_level_m,
            danger_level_m,
            extreme_level_m,
        )
        
        # Create current reading
        current = FloodGaugeCurrentBase(
            gauge_id=str(gauge.gauge_id),
            google_gauge_id=gauge.google_gauge_id,
            gauge_name=gauge.gauge_name,
            river_name=gauge.river_name,
            river_system=gauge.river_system,
            district=gauge.district,
            province=gauge.province,
            reading_time=reading_time,
            current_level_m=current_level_m,
            warning_level_m=warning_level_m,
            danger_level_m=danger_level_m,
            extreme_level_m=extreme_level_m,
            pct_of_warning=pct_of_warning,
            pct_of_danger=pct_of_danger,
            pct_of_historical_max=pct_of_historical_max,
            previous_level_m=previous_level_m,
            level_change_m=level_change_m,
            rise_rate_m_per_hour=rise_rate_m_per_hour,
            river_trend=river_trend,
            hours_to_warning=hours_to_warning,
            hours_to_danger=hours_to_danger,
            flood_status=flood_status,
            has_breach=False,
            breach_severity=None,
        )
        
        logger.debug(
            "Parsed current reading for %s: level=%.2fm, trend=%s, status=%s",
            gauge.gauge_name,
            current_level_m,
            river_trend,
            flood_status,
        )
        
        return current

    def _classify_river_trend(self, rise_rate_m_per_hour: float) -> str:
        """Classify river trend based on rise rate.
        
        Args:
            rise_rate_m_per_hour: Rate of level change (m/hour).
        
        Returns:
            Trend classification: rapidly_rising, rising, stable, falling, rapidly_falling.
        """
        if rise_rate_m_per_hour > 0.5:
            return "rapidly_rising"
        elif rise_rate_m_per_hour > 0.1:
            return "rising"
        elif rise_rate_m_per_hour >= -0.1:
            return "stable"
        elif rise_rate_m_per_hour >= -0.5:
            return "falling"
        else:
            return "rapidly_falling"

    def _determine_flood_status(
        self,
        current_level_m: float,
        warning_level_m: float | None,
        danger_level_m: float | None,
        extreme_level_m: float | None,
    ) -> str:
        """Determine flood status based on current level vs thresholds.
        
        Args:
            current_level_m: Current water level.
            warning_level_m: Warning threshold.
            danger_level_m: Danger threshold.
            extreme_level_m: Extreme threshold.
        
        Returns:
            Flood status: no_flooding, watch, warning, emergency.
        """
        if extreme_level_m and current_level_m >= extreme_level_m:
            return "emergency"
        elif danger_level_m and current_level_m >= danger_level_m:
            return "warning"
        elif warning_level_m and current_level_m >= warning_level_m:
            return "watch"
        else:
            return "no_flooding"

    # ── Forecast Parsing ──────────────────────────────────────────

    def parse_forecast(
        self,
        response: dict[str, Any],
        gauge: FloodGaugeRegistry,
    ) -> list[FloodGaugeForecastBase]:
        """Parse probabilistic flood forecasts from Google Flood Hub response.
        
        Args:
            response: Google Flood Hub API response.
            gauge: Flood gauge registry entry.
        
        Returns:
            List of flood gauge forecasts (p10/p50/p90).
        """
        forecasts = []
        
        # Extract forecast data (assuming response has 'forecasts' array)
        forecast_data = response.get("forecasts", [])
        
        if not forecast_data:
            logger.warning("No forecast data for gauge %s", gauge.gauge_name)
            return []
        
        today = datetime.now(_PKT).date()
        
        for item in forecast_data:
            try:
                # Parse forecast time
                forecast_time_str = item.get("timestamp")
                if not forecast_time_str:
                    continue
                
                forecast_dt = datetime.fromisoformat(forecast_time_str.replace("Z", "+00:00")).astimezone(_PKT)
                forecast_date = forecast_dt.date()
                
                # Calculate day offset and horizon
                day_offset = (forecast_date - today).days
                forecast_horizon_h = int((forecast_dt - datetime.now(_PKT)).total_seconds() / 3600)
                
                # Extract percentile levels
                level_p10_m = item.get("level_p10")
                level_p50_m = item.get("level_p50")
                level_p90_m = item.get("level_p90")
                
                if level_p50_m is None:
                    continue
                
                # Compute probabilities of exceeding thresholds
                prob_exceeds_warning_pct = None
                prob_exceeds_danger_pct = None
                
                # Determine forecast status (based on p50)
                forecast_status = self._determine_flood_status(
                    level_p50_m,
                    gauge.bankfull_level_m,  # Use bankfull as warning proxy
                    None,  # No danger level in registry
                    None,  # No extreme level in registry
                )
                
                # Determine worst case status (based on p90)
                worst_case_status = "normal"
                if level_p90_m:
                    worst_case_status = self._determine_flood_status(
                        level_p90_m,
                        gauge.bankfull_level_m,
                        None,
                        None,
                    )
                
                # Create forecast
                forecast = FloodGaugeForecastBase(
                    gauge_id=str(gauge.gauge_id),
                    google_gauge_id=gauge.google_gauge_id,
                    forecast_for_datetime=forecast_dt,
                    forecast_date=forecast_date,
                    day_offset=day_offset,
                    forecast_horizon_h=forecast_horizon_h,
                    level_p10_m=level_p10_m,
                    level_p50_m=level_p50_m,
                    level_p90_m=level_p90_m,
                    prob_exceeds_warning_pct=prob_exceeds_warning_pct,
                    prob_exceeds_danger_pct=prob_exceeds_danger_pct,
                    forecast_status=forecast_status,
                    worst_case_status=worst_case_status,
                    has_breach=False,
                    breach_severity=None,
                )
                
                forecasts.append(forecast)
                
            except Exception as e:
                logger.error("Failed to parse forecast item: %s", str(e))
                continue
        
        logger.info("Parsed %d forecasts for %s", len(forecasts), gauge.gauge_name)
        return forecasts

    # ── Breach Detection ──────────────────────────────────────────

    async def check_breach_current(
        self,
        current: FloodGaugeCurrentBase,
    ) -> tuple[bool, str | None]:
        """Check if current reading crosses thresholds.
        
        Args:
            current: Current flood gauge reading.
        
        Returns:
            Tuple of (has_breach, severity).
        """
        if not current.pct_of_danger:
            return False, None
        
        # Check pct_of_danger threshold
        threshold = self.breach_service.find_applicable_threshold(
            metric_name="pct_of_danger",
            disaster_kind="flood",
            province=current.province,
            district=current.district,
        )
        
        if threshold:
            severity = self.breach_service.check_breach(
                value=current.pct_of_danger,
                threshold=threshold,
            )
            
            if severity:
                await self.breach_service.create_breach(
                    source_api="google_flood_hub",
                    disaster_kind="flood",
                    metric_name="pct_of_danger",
                    observed_value=current.pct_of_danger,
                    threshold=threshold,
                    severity=severity,
                    observation_time=current.reading_time,
                    location_name=current.gauge_name,
                    district=current.district,
                    province=current.province,
                    latitude=0.0,  # Not available in current reading
                    longitude=0.0,
                    gauge_id=current.gauge_id,
                    is_forecast_breach=False,
                )
                
                return True, severity
        
        return False, None

    async def check_breach_forecast(
        self,
        forecast: FloodGaugeForecastBase,
        gauge: FloodGaugeRegistry,
    ) -> tuple[bool, str | None]:
        """Check if forecast crosses thresholds.
        
        Args:
            forecast: Flood gauge forecast.
            gauge: Flood gauge registry entry.
        
        Returns:
            Tuple of (has_breach, severity).
        """
        # For forecasts, we could check if p90 exceeds danger level
        # For now, we'll skip breach detection on forecasts
        return False, None

    # ── Data Processing ───────────────────────────────────────────

    async def process_current_reading(
        self,
        current: FloodGaugeCurrentBase,
    ) -> dict[str, Any]:
        """Process current reading: check breach and UPSERT.
        
        Args:
            current: Current flood gauge reading.
        
        Returns:
            Dictionary with processing statistics.
        """
        stats = {
            "gauge_name": current.gauge_name,
            "success": False,
            "breach_detected": False,
            "error": None,
        }
        
        try:
            # Check for breach
            has_breach, severity = await self.check_breach_current(current)
            current.has_breach = has_breach
            current.breach_severity = severity
            
            if has_breach:
                stats["breach_detected"] = True
            
            # UPSERT to database
            await self.flood_repo.upsert_current(current)
            stats["success"] = True
            
            logger.debug(
                "Processed current reading for %s: level=%.2fm, breach=%s",
                current.gauge_name,
                current.current_level_m,
                has_breach,
            )
            
        except Exception as e:
            logger.error("Failed to process current reading for %s: %s", current.gauge_name, str(e))
            stats["error"] = str(e)
        
        return stats

    async def process_forecasts(
        self,
        forecasts: list[FloodGaugeForecastBase],
        gauge: FloodGaugeRegistry,
    ) -> dict[str, Any]:
        """Process forecasts: check breaches and UPSERT.
        
        Args:
            forecasts: List of flood gauge forecasts.
            gauge: Flood gauge registry entry.
        
        Returns:
            Dictionary with processing statistics.
        """
        stats = {
            "gauge_name": gauge.gauge_name,
            "forecasts_processed": 0,
            "breaches_detected": 0,
            "errors": 0,
        }
        
        for forecast in forecasts:
            try:
                # Check for breach
                has_breach, severity = await self.check_breach_forecast(forecast, gauge)
                forecast.has_breach = has_breach
                forecast.breach_severity = severity
                
                if has_breach:
                    stats["breaches_detected"] += 1
                
                # UPSERT to database
                await self.flood_repo.upsert_forecast(forecast)
                stats["forecasts_processed"] += 1
                
            except Exception as e:
                logger.error("Failed to process forecast: %s", str(e))
                stats["errors"] += 1
                continue
        
        return stats
