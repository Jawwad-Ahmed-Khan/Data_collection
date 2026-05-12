"""
ClimaSync Collection Service — Google Flood Hub Service
"""

from __future__ import annotations

import json
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

    async def parse_current_data(
        self,
        data: dict[str, Any],
        gauge: FloodGaugeRegistry,
        previous_reading: FloodGaugeCurrentBase | None = None,
    ) -> FloodGaugeCurrentBase | None:
        """Parse current water level safely."""
        
        reading = data.get("latestReading")
        if reading is None:
            logger.warning(f"Gauge {gauge.google_gauge_id} missing latestReading")
            return None
            
        level = reading.get("gaugeValue")
        if level is None:
            logger.warning(f"Gauge {gauge.google_gauge_id} latestReading missing gaugeValue")
            return None
            
        # Unit conversion
        unit = reading.get("gaugeValueUnit", "METERS")
        if unit == "FEET":
            current_level_m = float(level) * 0.3048
        elif unit == "METERS":
            current_level_m = float(level)
        else:
            logger.warning(f"Unknown unit {unit} for gauge {gauge.google_gauge_id}, assuming METERS")
            current_level_m = float(level)
            
        # UTC Parsing with Z
        time_str = reading.get("issuedTime")
        if not time_str:
            logger.warning(f"Gauge {gauge.google_gauge_id} missing issuedTime")
            return None
            
        reading_time = datetime.fromisoformat(time_str.replace("Z", "+00:00")).astimezone(_PKT)
        reading_time_utc = reading_time.astimezone(ZoneInfo("UTC"))
        
        # Flood Status mapping
        status_raw = data.get("floodStatus", "NO_FLOODING").upper()
        status_map = {
            "NO_FLOODING": "no_flooding",
            "WATCH": "watch",
            "WARNING": "warning",
            "EMERGENCY": "emergency"
        }
        status_lower = status_map.get(status_raw, "no_flooding")
        if status_raw not in status_map:
            logger.warning(f"Unknown floodStatus {status_raw} for {gauge.google_gauge_id}")
            
        # D6. Threshold injection from registry
        warning_level_m = gauge.warning_level_m
        danger_level_m = gauge.danger_level_m
        extreme_level_m = gauge.extreme_level_m

        # D2. Percentage metrics
        pct_of_warning = round((current_level_m / warning_level_m) * 100, 3) if warning_level_m and warning_level_m > 0 else None
        pct_of_danger = round((current_level_m / danger_level_m) * 100, 3) if danger_level_m and danger_level_m > 0 else None
        pct_of_historical_max = round((current_level_m / gauge.historical_max_m) * 100, 3) if gauge.historical_max_m and gauge.historical_max_m > 0 else None

        # D1, D3, D4, D5. Previous Reading Math & Derived Metrics
        previous_level_m = None
        level_change_m = None
        rise_rate_m_per_hour = None
        river_trend = None
        hours_to_warning = None
        hours_to_danger = None
        
        if previous_reading:
            previous_level_m = previous_reading.current_level_m
            level_change_m = current_level_m - previous_level_m
            
            prev_time_utc = previous_reading.reading_time.astimezone(ZoneInfo("UTC"))
            time_diff_hours = (reading_time_utc - prev_time_utc).total_seconds() / 3600.0
            
            if time_diff_hours > 0:
                rise_rate_raw = level_change_m / time_diff_hours
                rise_rate_m_per_hour = round(rise_rate_raw, 4)
                
                # River trend classification
                if rise_rate_m_per_hour > 0.5:
                    river_trend = "rapidly_rising"
                elif rise_rate_m_per_hour > 0.1:
                    river_trend = "rising"
                elif rise_rate_m_per_hour >= -0.1:
                    river_trend = "stable"
                elif rise_rate_m_per_hour >= -0.5:
                    river_trend = "falling"
                else:
                    river_trend = "rapidly_falling"
                    
                # Hours to warning/danger (bounded)
                if river_trend in ("rising", "rapidly_rising") and rise_rate_m_per_hour > 0:
                    if warning_level_m and warning_level_m > 0 and current_level_m < warning_level_m:
                        hw = (warning_level_m - current_level_m) / rise_rate_m_per_hour
                        hours_to_warning = round(hw, 2) if hw <= 720 else None
                        
                    if danger_level_m and danger_level_m > 0 and current_level_m < danger_level_m:
                        hd = (danger_level_m - current_level_m) / rise_rate_m_per_hour
                        hours_to_danger = round(hd, 2) if hd <= 720 else None

        current = FloodGaugeCurrentBase(
            gauge_id=str(gauge.gauge_id),
            google_gauge_id=gauge.google_gauge_id,
            gauge_name=gauge.gauge_name or "Unnamed",
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
            river_trend=river_trend or "stable",
            hours_to_warning=hours_to_warning,
            hours_to_danger=hours_to_danger,
            flood_status=status_lower,
            has_breach=False,
            raw_api_response=data
        )
        return current

    async def process_current_reading(self, current: FloodGaugeCurrentBase, gauge: FloodGaugeRegistry) -> dict:
        try:
            logger.info(
                "Gauge %s: level=%.2fm, pct_danger=%.1f%%, trend=%s",
                gauge.google_gauge_id, current.current_level_m,
                current.pct_of_danger if current.pct_of_danger is not None else 0.0,
                current.river_trend
            )
            has_breach = False
            severity = None
            threshold_id = None
            
            # H1. Skip if pct_of_danger is None
            if current.pct_of_danger is not None:
                # H2. Find Threshold
                threshold = self.breach_service.find_applicable_threshold(
                    metric_name='gauge_pct_of_danger',
                    disaster_kind='flood',
                    province=current.province,
                    district=current.district
                )
                
                if threshold:
                    # Check Severity
                    severity = self.breach_service.check_breach(current.pct_of_danger, threshold)
                    
                    if severity:
                        has_breach = True
                        threshold_id = threshold.threshold_id
                        
                        # H4. Create Breach
                        await self.breach_service.create_breach(
                            source_api="google_flood_hub",
                            disaster_kind="flood",
                            metric_name="gauge_pct_of_danger",
                            observed_value=current.pct_of_danger,
                            threshold=threshold,
                            severity=severity,
                            observation_time=current.reading_time,
                            location_name=gauge.gauge_name,
                            district=gauge.district,
                            province=gauge.province,
                            latitude=gauge.latitude,
                            longitude=gauge.longitude,
                            gauge_id=gauge.gauge_id,
                            is_forecast_breach=False
                        )
            
            # H5. Set flags
            current.has_breach = has_breach
            current.breach_severity = severity
            current.threshold_id = threshold_id
            
            await self.flood_repo.upsert_current(current)
            return {"success": True, "breach_detected": has_breach}
        except Exception as e:
            logger.error(f"Failed to process current reading: {e}")
            return {"success": False, "breach_detected": False, "error": str(e)}

    async def parse_forecast_data(self, data: dict, gauge: FloodGaugeRegistry) -> list[FloodGaugeForecastBase]:
        """Parse forecast points safely, ensuring we grab the latest."""
        forecasts = data.get("forecasts", [])
        if not forecasts or not isinstance(forecasts, list):
            logger.debug(f"No valid forecasts array for {gauge.google_gauge_id}")
            return []
            
        # E1. Sort by issuedTime DESC
        def parse_issued_time(fc: dict) -> datetime:
            t = fc.get("issuedTime", "")
            try:
                return datetime.fromisoformat(t.replace("Z", "+00:00"))
            except Exception:
                return datetime.min.replace(tzinfo=ZoneInfo("UTC"))
            
        forecasts_sorted = sorted(forecasts, key=parse_issued_time, reverse=True)
        latest_forecast = forecasts_sorted[0]
        
        issued_at_utc = parse_issued_time(latest_forecast)
        if issued_at_utc == datetime.min.replace(tzinfo=ZoneInfo("UTC")):
            issued_at_utc = datetime.now(ZoneInfo("UTC"))
            
        issued_at_pkt = issued_at_utc.astimezone(_PKT)

        # E2. Extract levels
        levels = latest_forecast.get("levels", [])
        if not levels:
            logger.warning(f"Empty levels array for forecast {gauge.google_gauge_id}")
            return []
            
        now_utc = datetime.now(ZoneInfo("UTC"))
        window_end = now_utc + timedelta(days=5)
        parsed_forecasts = []
        
        for level_item in levels:
            valid_time_str = level_item.get("validTime")
            if not valid_time_str:
                continue
                
            try:
                valid_time_utc = datetime.fromisoformat(valid_time_str.replace("Z", "+00:00"))
            except Exception:
                continue
                
            # E3. Filter steps outside 5-day window or in the past
            if valid_time_utc <= now_utc or valid_time_utc > window_end:
                continue
                
            # E4. Filter steps where valid_time is before or equal to issued_time
            if valid_time_utc <= issued_at_utc:
                logger.debug(f"validTime <= issuedTime for {gauge.google_gauge_id}, skipping step")
                continue
                
            valid_time_pkt = valid_time_utc.astimezone(_PKT)
                
            level_entry = level_item.get("level", {})
            p50_raw = level_entry.get("value")
            if p50_raw is None:
                continue
                
            unit = level_entry.get("unit", "METERS")
            multiplier = 0.3048 if unit == "FEET" else 1.0
            
            p50_m = float(p50_raw) * multiplier
            
            percentiles = level_item.get("percentiles", {})
            p10_entry = percentiles.get("p10", {})
            p90_entry = percentiles.get("p90", {})
            
            p10_raw = p10_entry.get("value")
            p90_raw = p90_entry.get("value")
            
            p10_m = float(p10_raw) * multiplier if p10_raw is not None else p50_m
            p90_m = float(p90_raw) * multiplier if p90_raw is not None else p50_m
            
            diff = valid_time_utc - issued_at_utc
            hours = int(diff.total_seconds() / 3600)
            days = hours // 24
            
            # F1. Probability computation
            prob_exceeds_warning_pct = 0.0
            prob_exceeds_danger_pct = 0.0
            prob_exceeds_extreme_pct = 0.0
            
            if p50_m is None:
                prob_exceeds_warning_pct = None
                prob_exceeds_danger_pct = None
                prob_exceeds_extreme_pct = None
            else:
                # Warning
                if gauge.warning_level_m is None:
                    prob_exceeds_warning_pct = None
                elif p50_m >= gauge.warning_level_m:
                    prob_exceeds_warning_pct = 100.0
                elif p10_m is not None and p10_m >= gauge.warning_level_m:
                    prob_exceeds_warning_pct = 50.0
                    
                # Danger
                if gauge.danger_level_m is None:
                    prob_exceeds_danger_pct = None
                elif p50_m >= gauge.danger_level_m:
                    prob_exceeds_danger_pct = 100.0
                elif p10_m is not None and p10_m >= gauge.danger_level_m:
                    prob_exceeds_danger_pct = 50.0
                elif p90_m is not None and p90_m >= gauge.danger_level_m:
                    prob_exceeds_danger_pct = 10.0
                    
                # Extreme
                if gauge.extreme_level_m is None:
                    prob_exceeds_extreme_pct = None
                elif p50_m >= gauge.extreme_level_m:
                    prob_exceeds_extreme_pct = 100.0
                elif p90_m is not None and p90_m >= gauge.extreme_level_m:
                    prob_exceeds_extreme_pct = 10.0

            # F2. Status Classification
            forecast_status = 'no_flooding'
            worst_case_status = None
            
            if p50_m is not None:
                if gauge.extreme_level_m and p50_m >= gauge.extreme_level_m:
                    forecast_status = 'emergency'
                elif gauge.danger_level_m and p50_m >= gauge.danger_level_m:
                    forecast_status = 'emergency'
                elif gauge.warning_level_m and p50_m >= gauge.warning_level_m:
                    forecast_status = 'warning'
                    
            if p90_m is not None:
                worst_case_status = 'no_flooding'
                if gauge.extreme_level_m and p90_m >= gauge.extreme_level_m:
                    worst_case_status = 'emergency'
                elif gauge.danger_level_m and p90_m >= gauge.danger_level_m:
                    worst_case_status = 'emergency'
                elif gauge.warning_level_m and p90_m >= gauge.warning_level_m:
                    worst_case_status = 'warning'
            
            f = FloodGaugeForecastBase(
                gauge_id=str(gauge.gauge_id),
                google_gauge_id=gauge.google_gauge_id,
                gauge_name=gauge.gauge_name or "Unnamed",
                river_name=gauge.river_name,
                river_system=gauge.river_system,
                district=gauge.district,
                province=gauge.province,
                forecast_for_datetime=valid_time_pkt,
                forecast_issued_at=issued_at_pkt,
                forecast_date=valid_time_pkt.date(),
                day_offset=days,
                forecast_horizon_h=hours,
                level_p10_m=p10_m,
                level_p50_m=p50_m,
                level_p90_m=p90_m,
                prob_exceeds_warning_pct=prob_exceeds_warning_pct,
                prob_exceeds_danger_pct=prob_exceeds_danger_pct,
                prob_exceeds_extreme_pct=prob_exceeds_extreme_pct,
                forecast_status=forecast_status,
                worst_case_status=worst_case_status or 'no_flooding',
                raw_api_response=data
            )
            parsed_forecasts.append(f)
            
        # E5. Empty forecast after filtering
        if not parsed_forecasts:
            logger.warning(f"All forecast steps filtered out for {gauge.google_gauge_id}")
            return []
            
        logger.info(f"Parsed {len(parsed_forecasts)} forecast points for {gauge.google_gauge_id}")
        return parsed_forecasts

    async def process_forecasts(self, forecasts: list[FloodGaugeForecastBase], gauge: FloodGaugeRegistry) -> dict:
        try:
            if not forecasts:
                return {"success": True, "count": 0}
                
            threshold = self.breach_service.find_applicable_threshold(
                metric_name='gauge_pct_of_danger',
                disaster_kind='flood',
                province=gauge.province,
                district=gauge.district
            )
            
            if threshold:
                # I1. One breach per severity level per gauge
                breaches_created = {} # severity -> breach_id
                
                # Sort earliest to latest
                sorted_forecasts = sorted(forecasts, key=lambda r: r.forecast_for_datetime)
                now_utc = datetime.now(ZoneInfo("UTC"))
                
                for step in sorted_forecasts:
                    if gauge.danger_level_m is None or gauge.danger_level_m <= 0:
                        continue
                        
                    pct = (step.level_p50_m / gauge.danger_level_m) * 100
                    severity = self.breach_service.check_breach(pct, threshold)
                    
                    if severity:
                        # Only create breach if this severity not yet created for this gauge
                        if severity not in breaches_created:
                            # I3. Duplicate check for forecast
                            existing = await self.breach_service.check_duplicate(
                                location_id=gauge.gauge_id,
                                metric_name='gauge_pct_of_danger',
                                metric_category='flood_gauge',
                                severity=severity,
                                is_forecast_breach=True
                            )
                            if existing:
                                # Suppressed
                                step.has_forecast_breach = True
                                step.breach_severity = severity
                                step.threshold_id = threshold.threshold_id
                            else:
                                diff = step.forecast_for_datetime.astimezone(ZoneInfo("UTC")) - now_utc
                                horizon_h = int(diff.total_seconds() / 3600)
                                if horizon_h > 0:
                                    # I2. Insert forecast breach
                                    breach_id = await self.breach_service.create_breach(
                                        source_api="google_flood_hub",
                                        disaster_kind="flood",
                                        metric_name="gauge_pct_of_danger",
                                        observed_value=pct,
                                        threshold=threshold,
                                        severity=severity,
                                        observation_time=step.forecast_for_datetime,
                                        location_name=gauge.gauge_name,
                                        district=gauge.district,
                                        province=gauge.province,
                                        latitude=gauge.latitude,
                                        longitude=gauge.longitude,
                                        gauge_id=gauge.gauge_id,
                                        is_forecast_breach=True,
                                        forecast_horizon_h=horizon_h
                                    )
                                    breaches_created[severity] = breach_id
                                    
                                    step.has_forecast_breach = True
                                    step.breach_severity = severity
                                    step.threshold_id = threshold.threshold_id
                        else:
                            # I4. Already created a breach for this severity in this cycle (duplicate suppression)
                            step.has_forecast_breach = True
                            step.breach_severity = severity
                            step.threshold_id = threshold.threshold_id

            await self.flood_repo.upsert_forecast_batch(forecasts)
            logger.info("Wrote %d forecast steps for %s", len(forecasts), gauge.google_gauge_id)
            return {"success": True, "count": len(forecasts)}
        except Exception as e:
            logger.error(f"Failed to process forecasts: {e}")
            return {"success": False, "error": str(e)}
