"""
ClimaSync Collection Service — Google Flood Hub Service
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
_PKT = ZoneInfo("Asia/Karachi")


class FloodHubService:
    def __init__(self, flood_repo: FloodRepository, breach_service: BreachService) -> None:
        self.flood_repo = flood_repo
        self.breach_service = breach_service
        logger.info("FloodHubService initialized")

    async def parse_v1_current(
        self,
        data: dict[str, Any],
        gauge: FloodGaugeRegistry,
        previous_reading: FloodGaugeCurrentBase | None = None,
    ) -> FloodGaugeCurrentBase | None:
        """Parse current water level from V1 API forecast response.
        
        The current reading is typically the first point in the forecast array.
        """
        # data is the object for this gauge, which contains 'forecasts' (list of ForecastSet)
        forecast_sets = data.get("forecasts", [])
        if not forecast_sets:
            logger.warning(f"No forecast sets for gauge {gauge.google_gauge_id}")
            return None
            
        # Each ForecastSet can have forecastTimedValues OR forecastRanges
        # We'll check both
        f_set = forecast_sets[0]
        timed_values = f_set.get("forecastTimedValues", [])
        ranges = f_set.get("forecastRanges", [])
        
        current_level_m = 0.0
        reading_time = datetime.now(_PKT)

        if timed_values:
            latest_point = timed_values[0]
            current_level_m = float(latest_point.get("value", 0.0))
            reading_time_str = latest_point.get("startTime")
            if reading_time_str:
                reading_time = datetime.fromisoformat(reading_time_str.replace("Z", "+00:00")).astimezone(_PKT)
        elif ranges:
            latest_range = ranges[0]
            current_level_m = float(latest_range.get("value", 0.0))
            reading_time_str = latest_range.get("forecastStartTime")
            if reading_time_str:
                reading_time = datetime.fromisoformat(reading_time_str.replace("Z", "+00:00")).astimezone(_PKT)
        else:
            logger.warning(f"No timed values or ranges for gauge {gauge.google_gauge_id}")
            return None

        # Derived metrics logic (Simplified for demo)
        pct_of_danger = None
        if gauge.danger_level_m and gauge.danger_level_m > 0:
            pct_of_danger = (current_level_m / float(gauge.danger_level_m)) * 100.0

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
            pct_of_danger=pct_of_danger,
            flood_status="no_flooding",
            has_breach=False,
        )
        return current

    # Shared logic with legacy parser
    async def process_current_reading(self, current: FloodGaugeCurrentBase) -> dict:
        try:
            # Check for breach
            has_breach = False
            severity = None
            if current.pct_of_danger and current.pct_of_danger >= 100:
                has_breach = True
                severity = "warning"
            
            current.has_breach = has_breach
            current.breach_severity = severity
            
            await self.flood_repo.upsert_current(current)
            return {"success": True, "breach_detected": has_breach}
        except Exception as e:
            logger.error(f"Failed to process current reading: {e}")
            return {"success": False, "breach_detected": False, "error": str(e)}

    async def parse_forecast_data(self, data: dict, gauge: FloodGaugeRegistry) -> list[FloodGaugeForecastBase]:
        """Parse all forecast points from V1 API response."""
        forecast_sets = data.get("forecasts", [])
        if not forecast_sets:
            return []
            
        f_set = forecast_sets[0]
        issued_time_str = f_set.get("issuedTime")
        issued_at = datetime.now(_PKT)
        if issued_time_str:
            issued_at = datetime.fromisoformat(issued_time_str.replace("Z", "+00:00")).astimezone(_PKT)

        timed_values = f_set.get("forecastTimedValues", [])
        ranges = f_set.get("forecastRanges", [])
        
        parsed_forecasts = []
        
        # Helper to create forecast object
        def create_forecast(val: float, start_str: str):
            f_time = datetime.fromisoformat(start_str.replace("Z", "+00:00")).astimezone(_PKT)
            
            # Calculate offsets relative to issued time
            diff = f_time - issued_at
            hours = int(diff.total_seconds() / 3600)
            days = hours // 24
            
            # DEBUG
            print(f"DEBUG: Calculated hours={hours} for {f_time} (issued: {issued_at})")
            
            # Skip historical points to satisfy DB constraints (day_offset >= 0)
            if hours < 0:
                return None
                
            return FloodGaugeForecastBase(
                gauge_id=str(gauge.gauge_id),
                google_gauge_id=gauge.google_gauge_id,
                gauge_name=gauge.gauge_name,
                river_name=gauge.river_name,
                river_system=gauge.river_system,
                district=gauge.district,
                province=gauge.province,
                forecast_for_datetime=f_time,
                forecast_issued_at=issued_at,
                forecast_date=f_time.date(),
                day_offset=days,
                forecast_horizon_h=hours,
                level_p50_m=val,
                forecast_status="no_flooding"
            )

        if timed_values:
            for i, p in enumerate(timed_values):
                f = create_forecast(float(p.get("value", 0.0)), p.get("startTime"))
                if f: parsed_forecasts.append(f)
        elif ranges:
            for i, r in enumerate(ranges):
                f = create_forecast(float(r.get("value", 0.0)), r.get("forecastStartTime"))
                if f: parsed_forecasts.append(f)
                
        logger.info(f"Parsed {len(parsed_forecasts)} forecast points for {gauge.google_gauge_id}")
        return parsed_forecasts

    async def process_forecasts(self, forecasts: list[FloodGaugeForecastBase]) -> dict:
        """Upsert all parsed forecast points."""
        try:
            for f in forecasts:
                await self.flood_repo.upsert_forecast(f)
            logger.info(f"Successfully upserted {len(forecasts)} forecast points")
            return {"success": True, "count": len(forecasts)}
        except Exception as e:
            logger.error(f"Failed to process forecasts: {e}")
            return {"success": False, "error": str(e)}
