"""
ClimaSync Collection Service — Open-Meteo Weather Service

Parses Open-Meteo API responses and processes weather data.

Key responsibilities:
  - Build hourly and daily query parameters
  - Parse hourly and daily weather data
  - Compute rolling precipitation sums (24h, 72h)
  - Set weather flags (extreme heat, heatwave, heavy rain, storm)
  - Check for threshold breaches
  - UPSERT weather data to database

Note: This is a simplified implementation focusing on core functionality.
Full implementation would include all 19 hourly + 14 daily variables.
"""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime, date, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.core.logger import get_logger
from app.models.weather_models import (
    WeatherHourlyWindowBase, 
    WeatherDailySummaryBase,
    CurrentWeatherLocationBase,
    Weather5DaySummaryBase
)
from app.models.reference_models import PakistanLocation
from app.repositories.weather_repository import WeatherRepository
from app.services.breach_service import BreachService

logger = get_logger(__name__)

# Pakistan Standard Time
_PKT = ZoneInfo("Asia/Karachi")


def to_decimal(value: Any) -> Decimal | None:
    """
    Safely convert value to Decimal.
    
    Returns None if input is None or invalid.
    """
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (ValueError, TypeError):
        return None


class OpenMeteoService:
    """Processes Open-Meteo weather data.
    
    Parses API responses, computes rolling sums, sets flags,
    checks breaches, and stores data in database.
    """

    def __init__(
        self,
        weather_repo: WeatherRepository,
        breach_service: BreachService,
    ) -> None:
        """Initialize Open-Meteo service.
        
        Args:
            weather_repo: Repository for storing weather data.
            breach_service: Service for checking threshold breaches.
        """
        self.weather_repo = weather_repo
        self.breach_service = breach_service
        
        logger.info("OpenMeteoService initialized")

    # ── Query Parameter Building ──────────────────────────────────

    def build_batch_params(
        self,
        locations: list[PakistanLocation],
    ) -> dict[str, Any]:
        """Build Open-Meteo batch query parameters for multiple locations.
        
        Open-Meteo supports batch requests by passing comma-separated
        latitude and longitude values. This allows fetching up to 10
        locations in a single API call.
        
        Args:
            locations: List of Pakistan locations (max 10).
        
        Returns:
            Dictionary of batch query parameters.
        """
        if len(locations) > 10:
            raise ValueError("Open-Meteo batch API supports max 10 locations per request")
        
        # Extract coordinates
        latitudes = [str(loc.latitude) for loc in locations]
        longitudes = [str(loc.longitude) for loc in locations]
        
        # All hourly and daily variables
        hourly_vars = [
            "temperature_2m",
            "apparent_temperature",
            "dew_point_2m",
            "precipitation",
            "precipitation_probability",
            "rain",
            "snowfall",
            "snow_depth",
            "wind_speed_10m",
            "wind_gusts_10m",
            "wind_direction_10m",
            "relative_humidity_2m",
            "surface_pressure",
            "visibility",
            "cloud_cover",
            "uv_index",
            "cape",
            "weather_code",
            "is_day",
        ]
        
        daily_vars = [
            "temperature_2m_max",
            "temperature_2m_min",
            "apparent_temperature_max",
            "apparent_temperature_min",
            "precipitation_sum",
            "rain_sum",
            "snowfall_sum",
            "precipitation_hours",
            "precipitation_probability_max",
            "wind_speed_10m_max",
            "wind_gusts_10m_max",
            "wind_direction_10m_dominant",
            "uv_index_max",
            "sunrise",
            "sunset",
            "daylight_duration",
            "weather_code",
        ]
        
        return {
            "latitude": ",".join(latitudes),
            "longitude": ",".join(longitudes),
            "hourly": ",".join(hourly_vars),
            "daily": ",".join(daily_vars),
            "timezone": "Asia/Karachi",
            "forecast_days": 5,
        }

    def build_hourly_params(
        self,
        latitude: float,
        longitude: float,
    ) -> dict[str, Any]:
        """Build Open-Meteo hourly query parameters.
        
        Args:
            latitude: Location latitude.
            longitude: Location longitude.
        
        Returns:
            Dictionary of query parameters.
        """
        # Core hourly variables (simplified - full implementation would have all 19)
        hourly_vars = [
            "temperature_2m",
            "apparent_temperature",
            "dew_point_2m",
            "precipitation",
            "precipitation_probability",
            "rain",
            "snowfall",
            "snow_depth",
            "wind_speed_10m",
            "wind_gusts_10m",
            "wind_direction_10m",
            "relative_humidity_2m",
            "surface_pressure",
            "visibility",
            "cloud_cover",
            "uv_index",
            "cape",
            "weather_code",
            "is_day",
        ]
        
        return {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": ",".join(hourly_vars),
            "timezone": "Asia/Karachi",
            "forecast_days": 5,
        }

    def build_daily_params(
        self,
        latitude: float,
        longitude: float,
    ) -> dict[str, Any]:
        """Build Open-Meteo daily query parameters.
        
        Args:
            latitude: Location latitude.
            longitude: Location longitude.
        
        Returns:
            Dictionary of query parameters.
        """
        # Core daily variables (simplified - full implementation would have all 14)
        daily_vars = [
            "temperature_2m_max",
            "temperature_2m_min",
            "apparent_temperature_max",
            "apparent_temperature_min",
            "precipitation_sum",
            "rain_sum",
            "snowfall_sum",
            "precipitation_hours",
            "precipitation_probability_max",
            "wind_speed_10m_max",
            "wind_gusts_10m_max",
            "wind_direction_10m_dominant",
            "uv_index_max",
            "sunrise",
            "sunset",
            "daylight_duration",
            "weather_code",
        ]
        
        return {
            "latitude": latitude,
            "longitude": longitude,
            "daily": ",".join(daily_vars),
            "timezone": "Asia/Karachi",
            "forecast_days": 5,
        }

    # ── Hourly Data Parsing ───────────────────────────────────────

    def parse_hourly(
        self,
        response: dict[str, Any],
        location: PakistanLocation,
    ) -> list[WeatherHourlyWindowBase]:
        """Parse hourly weather data from Open-Meteo response.
        
        Args:
            response: Open-Meteo API response.
            location: Pakistan location.
        
        Returns:
            List of hourly weather records.
        """
        hourly_data = response.get("hourly", {})
        times = hourly_data.get("time", [])
        
        if not times:
            logger.warning("No hourly data for location %s", location.location_name)
            return []
        
        records = []
        
        for i, time_str in enumerate(times):
            try:
                # Parse timestamp
                forecast_dt = datetime.fromisoformat(time_str).replace(tzinfo=_PKT)
                forecast_date = forecast_dt.date()
                
                # Calculate day offset
                today = datetime.now(_PKT).date()
                day_offset = (forecast_date - today).days
                
                # Extract values (with safe indexing)
                # double precision columns: convert to float
                temp_c = to_decimal(self._safe_get(hourly_data.get("temperature_2m"), i))
                temp_apparent_c = to_decimal(self._safe_get(hourly_data.get("apparent_temperature"), i))
                temp_dewpoint_c = to_decimal(self._safe_get(hourly_data.get("dew_point_2m"), i))
                precip_mm = to_decimal(self._safe_get(hourly_data.get("precipitation"), i, 0.0))
                rain_mm = to_decimal(self._safe_get(hourly_data.get("rain"), i))
                snowfall_cm = to_decimal(self._safe_get(hourly_data.get("snowfall"), i))
                snow_depth_m = to_decimal(self._safe_get(hourly_data.get("snow_depth"), i))
                wind_speed_kmh = to_decimal(self._safe_get(hourly_data.get("wind_speed_10m"), i))
                wind_gusts_kmh = to_decimal(self._safe_get(hourly_data.get("wind_gusts_10m"), i))
                pressure_hpa = to_decimal(self._safe_get(hourly_data.get("surface_pressure"), i))
                uv_index = to_decimal(self._safe_get(hourly_data.get("uv_index"), i))
                cape_jkg = to_decimal(self._safe_get(hourly_data.get("cape"), i))
                
                # SMALLINT/INT columns: keep as-is
                precip_prob_pct = self._safe_get(hourly_data.get("precipitation_probability"), i)
                wind_direction_deg = self._safe_get(hourly_data.get("wind_direction_10m"), i)
                humidity_pct = self._safe_get(hourly_data.get("relative_humidity_2m"), i)
                visibility_m = self._safe_get(hourly_data.get("visibility"), i)
                cloud_cover_pct = self._safe_get(hourly_data.get("cloud_cover"), i)
                weather_code = self._safe_get(hourly_data.get("weather_code"), i)
                is_daytime = self._safe_get(hourly_data.get("is_day"), i, 1) == 1
                
                # Compute wind cardinal direction
                wind_cardinal = self._wind_to_cardinal(wind_direction_deg) if wind_direction_deg is not None else None
                
                # Decode weather condition
                weather_condition, weather_description = self._decode_weather_code(weather_code)
                
                # Create record
                record = WeatherHourlyWindowBase(
                    location_id=location.location_id,
                    location_key=location.location_key,
                    location_name=location.location_name,
                    district=location.district,
                    province=location.province,
                    latitude=location.latitude,
                    longitude=location.longitude,
                    forecast_for_datetime=forecast_dt,
                    forecast_date=forecast_date,
                    day_offset=day_offset,
                    temp_c=temp_c,
                    temp_apparent_c=temp_apparent_c,
                    temp_dewpoint_c=temp_dewpoint_c,
                    precip_mm=precip_mm,
                    precip_prob_pct=precip_prob_pct,
                    rain_mm=rain_mm,
                    snowfall_cm=snowfall_cm,
                    snow_depth_m=snow_depth_m,
                    wind_speed_kmh=wind_speed_kmh,
                    wind_gusts_kmh=wind_gusts_kmh,
                    wind_direction_deg=wind_direction_deg,
                    wind_direction_cardinal=wind_cardinal,
                    humidity_pct=humidity_pct,
                    pressure_hpa=pressure_hpa,
                    visibility_m=visibility_m,
                    cloud_cover_pct=cloud_cover_pct,
                    uv_index=uv_index,
                    cape_jkg=cape_jkg,
                    weather_code=weather_code,
                    weather_condition=weather_condition,
                    weather_description=weather_description,
                    is_daytime=is_daytime,
                )
                
                records.append(record)
                
            except Exception as e:
                logger.error("Failed to parse hourly record %d: %s", i, str(e))
                continue
        
        # Compute rolling sums
        self._compute_rolling_sums(records)
        
        # Set weather flags
        for record in records:
            self._set_weather_flags(record)
        
        logger.info("Parsed %d hourly records for %s", len(records), location.location_name)
        return records

    def _safe_get(self, array: list | None, index: int, default: Any = None) -> Any:
        """Safely get value from array at index."""
        if array is None or index >= len(array):
            return default
        value = array[index]
        return value if value is not None else default

    def _compute_rolling_sums(self, records: list[WeatherHourlyWindowBase]) -> None:
        """Compute rolling precipitation sums (3h, 6h, 12h, 24h, 72h) for each record."""
        for i, record in enumerate(records):
            # Helper for rolling sum computation
            def get_rolling_sum(window_size: int) -> Decimal:
                total = Decimal(0)
                for j in range(max(0, i - window_size + 1), i + 1):
                    val = records[j].precip_mm
                    if val is not None:
                        total += Decimal(str(val))
                return total if total > 0 else Decimal(0)

            record.precip_3h_mm = get_rolling_sum(3)
            record.precip_6h_mm = get_rolling_sum(6)
            record.precip_12h_mm = get_rolling_sum(12)
            record.precip_24h_mm = get_rolling_sum(24)
            record.precip_72h_mm = get_rolling_sum(72)

    def _set_weather_flags(self, record: WeatherHourlyWindowBase) -> None:
        """Set weather flags based on thresholds."""
        # Extreme heat (>45°C)
        if record.temp_c is not None and record.temp_c >= Decimal("45.0"):
            record.flag_extreme_heat = True
        
        # Heatwave (>40°C)
        if record.temp_c is not None and record.temp_c >= Decimal("40.0"):
            record.flag_heatwave = True
        
        # Heavy rain (>50mm in 24h)
        if record.precip_24h_mm is not None and record.precip_24h_mm >= Decimal("50.0"):
            record.flag_heavy_rain = True
        
        # Very heavy rain (>100mm in 24h)
        if record.precip_24h_mm is not None and record.precip_24h_mm >= Decimal("100.0"):
            record.flag_very_heavy_rain = True
        
        # Storm (wind gusts >60 km/h)
        if record.wind_gusts_kmh is not None and record.wind_gusts_kmh >= Decimal("60.0"):
            record.flag_storm = True
        
        # Severe storm (wind gusts >90 km/h)
        if record.wind_gusts_kmh is not None and record.wind_gusts_kmh >= Decimal("90.0"):
            record.flag_severe_storm = True
        
        # Cold wave (<5°C)
        if record.temp_c is not None and record.temp_c <= Decimal("5.0"):
            record.flag_cold_wave = True
        
        # Dust storm (weather code indicates dust + high wind)
        # WMO codes for dust/sand: Not in standard codes, but we check for clear/haze + high wind
        if record.wind_speed_kmh is not None and record.wind_speed_kmh >= Decimal("40.0"):
            # Dust storm likely if high wind + low visibility + clear/haze conditions
            if record.visibility_m is not None and record.visibility_m < 1000:
                if record.weather_condition in ['clear', 'haze', 'partly_cloudy']:
                    record.flag_dust_storm = True
        
        # Dense fog (weather code indicates fog + low visibility)
        if record.weather_condition == 'fog':
            if record.visibility_m is not None and record.visibility_m < 200:
                record.flag_dense_fog = True

    def _wind_to_cardinal(self, degrees: int | float) -> str:
        """Convert wind direction degrees to cardinal direction."""
        directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        index = round(float(degrees) / 45) % 8
        return directions[index]

    def _decode_weather_code(self, code: int | None) -> tuple[str | None, str | None]:
        """Decode WMO weather code to condition and description."""
        if code is None:
            return None, None
        
        # Simplified WMO code mapping
        code_map = {
            0: ("clear", "Clear sky"),
            1: ("partly_cloudy", "Mainly clear"),
            2: ("partly_cloudy", "Partly cloudy"),
            3: ("overcast", "Overcast"),
            45: ("fog", "Fog"),
            48: ("fog", "Depositing rime fog"),
            51: ("drizzle", "Light drizzle"),
            53: ("drizzle", "Moderate drizzle"),
            55: ("drizzle", "Dense drizzle"),
            61: ("rain", "Slight rain"),
            63: ("rain", "Moderate rain"),
            65: ("heavy_rain", "Heavy rain"),
            71: ("snow", "Slight snow"),
            73: ("snow", "Moderate snow"),
            75: ("heavy_snow", "Heavy snow"),
            80: ("rain_showers", "Slight rain showers"),
            81: ("rain_showers", "Moderate rain showers"),
            82: ("rain_showers", "Violent rain showers"),
            95: ("thunderstorm", "Thunderstorm"),
            96: ("thunderstorm_with_hail", "Thunderstorm with slight hail"),
            99: ("thunderstorm_with_hail", "Thunderstorm with heavy hail"),
        }
        
        condition, description = code_map.get(code, ("unknown", f"Weather code {code}"))
        return condition, description

    # ── Daily Data Parsing ────────────────────────────────────────

    def parse_daily(
        self,
        response: dict[str, Any],
        location: PakistanLocation,
    ) -> list[WeatherDailySummaryBase]:
        """Parse daily weather summaries from Open-Meteo response.
        
        Args:
            response: Open-Meteo API response.
            location: Pakistan location.
        
        Returns:
            List of daily weather summaries.
        """
        daily_data = response.get("daily", {})
        times = daily_data.get("time", [])
        
        if not times:
            logger.warning("No daily data for location %s", location.location_name)
            return []
        
        summaries = []
        today = datetime.now(_PKT).date()
        
        for i, time_str in enumerate(times):
            try:
                summary_date = date.fromisoformat(time_str)
                day_offset = (summary_date - today).days
                
                # Extract values
                # double precision columns: convert to float
                temp_max_c = to_decimal(self._safe_get(daily_data.get("temperature_2m_max"), i))
                temp_min_c = to_decimal(self._safe_get(daily_data.get("temperature_2m_min"), i))
                feels_like_max_c = to_decimal(self._safe_get(daily_data.get("apparent_temperature_max"), i))
                feels_like_min_c = to_decimal(self._safe_get(daily_data.get("apparent_temperature_min"), i))
                
                precip_total_mm = to_decimal(self._safe_get(daily_data.get("precipitation_sum"), i, 0.0))
                rain_total_mm = to_decimal(self._safe_get(daily_data.get("rain_sum"), i))
                snowfall_total_cm = to_decimal(self._safe_get(daily_data.get("snowfall_sum"), i))
                precip_hours = self._safe_get(daily_data.get("precipitation_hours"), i)
                precip_prob_max_pct = self._safe_get(daily_data.get("precipitation_probability_max"), i)
                
                wind_speed_max_kmh = to_decimal(self._safe_get(daily_data.get("wind_speed_10m_max"), i))
                wind_gusts_max_kmh = to_decimal(self._safe_get(daily_data.get("wind_gusts_10m_max"), i))
                wind_dir_dominant = self._safe_get(daily_data.get("wind_direction_10m_dominant"), i)
                
                uv_index_max = to_decimal(self._safe_get(daily_data.get("uv_index_max"), i))
                
                # Day Overview
                weather_code_daily = self._safe_get(daily_data.get("weather_code"), i)
                dominant_condition, _ = self._decode_weather_code(weather_code_daily)
                
                # daylight_duration is in seconds, convert to hours
                daylight_duration_s = to_decimal(self._safe_get(daily_data.get("daylight_duration"), i))
                daylight_hours = (daylight_duration_s / Decimal("3600.0")).quantize(Decimal("0.01")) if daylight_duration_s is not None else None

                # Parse sunrise/sunset
                sunrise_str = self._safe_get(daily_data.get("sunrise"), i)
                sunset_str = self._safe_get(daily_data.get("sunset"), i)
                sunrise_at = datetime.fromisoformat(sunrise_str).replace(tzinfo=_PKT) if sunrise_str else None
                sunset_at = datetime.fromisoformat(sunset_str).replace(tzinfo=_PKT) if sunset_str else None
                
                # Create summary
                summary = WeatherDailySummaryBase(
                    location_id=location.location_id,
                    location_key=location.location_key,
                    location_name=location.location_name,
                    district=location.district,
                    province=location.province,
                    latitude=location.latitude,
                    longitude=location.longitude,
                    summary_date=summary_date,
                    day_offset=day_offset,
                    temp_max_c=temp_max_c,
                    temp_min_c=temp_min_c,
                    feels_like_max_c=feels_like_max_c,
                    feels_like_min_c=feels_like_min_c,
                    precip_total_mm=precip_total_mm,
                    rain_total_mm=rain_total_mm,
                    snowfall_total_cm=snowfall_total_cm,
                    precip_hours=precip_hours,
                    precip_prob_max_pct=precip_prob_max_pct,
                    wind_speed_max_kmh=wind_speed_max_kmh,
                    wind_gusts_max_kmh=wind_gusts_max_kmh,
                    wind_dominant_cardinal=self._wind_to_cardinal(wind_dir_dominant) if wind_dir_dominant is not None else None,
                    uv_index_max=uv_index_max,
                    sunrise_at=sunrise_at,
                    sunset_at=sunset_at,
                    daylight_hours=daylight_hours,
                    dominant_condition=dominant_condition,
                    weather_code_dominant=weather_code_daily,
                )
                
                # Set daily flags
                self._set_daily_flags(summary)
                
                summaries.append(summary)
                
            except Exception as e:
                logger.error("Failed to parse daily record %d: %s", i, str(e))
                continue
        
        logger.info("Parsed %d daily summaries for %s", len(summaries), location.location_name)
        return summaries

    def _set_daily_flags(self, summary: WeatherDailySummaryBase) -> None:
        """Set daily weather flags based on thresholds."""
        if summary.temp_max_c is not None and summary.temp_max_c >= Decimal("45.0"):
            summary.flag_extreme_heat_day = True
        
        if summary.temp_max_c is not None and summary.temp_max_c >= Decimal("40.0"):
            summary.flag_heatwave_day = True
        
        if summary.precip_total_mm is not None and summary.precip_total_mm >= Decimal("50.0"):
            summary.flag_heavy_rain_day = True
        
        if summary.wind_gusts_max_kmh is not None and summary.wind_gusts_max_kmh >= Decimal("60.0"):
            summary.flag_storm_day = True
        
        if summary.temp_min_c is not None and summary.temp_min_c <= Decimal("5.0"):
            summary.flag_cold_wave_day = True

    # ── Breach Detection ──────────────────────────────────────────

    async def check_breaches(
        self,
        record: WeatherHourlyWindowBase,
    ) -> list[tuple[bool, str | None, str | None, Decimal | None, Decimal | None]]:
        """Check if weather metrics cross thresholds for ALL disaster types.
        
        Checks for:
        1. Heatwave (temp_max_c)
        2. Heavy Rain (precip_1h_mm, precip_24h_mm, precip_72h_mm)
        3. Cyclone/Storm (wind_gusts_kmh, cape_jkg)
        4. Cold Wave (temp_min_c)
        5. Dust Storm (wind_speed + visibility)
        6. Flash Flood (precip_accumulation)
        7. Drought (not applicable to hourly data)
        
        Args:
            record: Hourly weather record.
        
        Returns:
            List of tuples: (has_breach, severity, metric_name, observed_value, threshold_value)
        """
        breaches = []
        
        # 1. HEATWAVE - Check temperature thresholds
        if record.temp_c is not None:
            threshold = self.breach_service.find_applicable_threshold(
                metric_name="temp_max_c",
                disaster_kind="heatwave",
                province=record.province,
                district=record.district,
            )
            
            if threshold:
                severity = self.breach_service.check_breach(
                    value=float(record.temp_c),
                    threshold=threshold,
                )
                
                if severity:
                    threshold_value = self.breach_service._get_threshold_value(threshold, severity)
                    breaches.append((True, severity, "temp_max_c", record.temp_c, Decimal(str(threshold_value))))
        
        # 2. HEAVY RAIN - Check hourly precipitation
        if record.precip_mm is not None and record.precip_mm > 0:
            threshold = self.breach_service.find_applicable_threshold(
                metric_name="precip_1h_mm",
                disaster_kind="heavy_rain",
                province=record.province,
                district=record.district,
            )
            
            if threshold:
                severity = self.breach_service.check_breach(
                    value=float(record.precip_mm),
                    threshold=threshold,
                )
                
                if severity:
                    threshold_value = self.breach_service._get_threshold_value(threshold, severity)
                    breaches.append((True, severity, "precip_1h_mm", record.precip_mm, Decimal(str(threshold_value))))
        
        # 3. HEAVY RAIN - Check 24-hour accumulation
        if record.precip_24h_mm is not None and record.precip_24h_mm > 0:
            threshold = self.breach_service.find_applicable_threshold(
                metric_name="precip_24h_mm",
                disaster_kind="heavy_rain",
                province=record.province,
                district=record.district,
            )
            
            if threshold:
                severity = self.breach_service.check_breach(
                    value=float(record.precip_24h_mm),
                    threshold=threshold,
                )
                
                if severity:
                    threshold_value = self.breach_service._get_threshold_value(threshold, severity)
                    breaches.append((True, severity, "precip_24h_mm", record.precip_24h_mm, Decimal(str(threshold_value))))
        
        # 4. FLASH FLOOD - Check 72-hour accumulation
        if record.precip_72h_mm is not None and record.precip_72h_mm > 0:
            threshold = self.breach_service.find_applicable_threshold(
                metric_name="precip_72h_mm",
                disaster_kind="flash_flood",
                province=record.province,
                district=record.district,
            )
            
            if threshold:
                severity = self.breach_service.check_breach(
                    value=float(record.precip_72h_mm),
                    threshold=threshold,
                )
                
                if severity:
                    threshold_value = self.breach_service._get_threshold_value(threshold, severity)
                    breaches.append((True, severity, "precip_72h_mm", record.precip_72h_mm, Decimal(str(threshold_value))))
        
        # 5. CYCLONE/STORM - Check wind gusts
        if record.wind_gusts_kmh is not None:
            threshold = self.breach_service.find_applicable_threshold(
                metric_name="wind_gusts_kmh",
                disaster_kind="cyclone",
                province=record.province,
                district=record.district,
            )
            
            if threshold:
                severity = self.breach_service.check_breach(
                    value=float(record.wind_gusts_kmh),
                    threshold=threshold,
                )
                
                if severity:
                    threshold_value = self.breach_service._get_threshold_value(threshold, severity)
                    breaches.append((True, severity, "wind_gusts_kmh", record.wind_gusts_kmh, Decimal(str(threshold_value))))
        
        # 6. SEVERE STORM - Check CAPE (Convective Available Potential Energy)
        if record.cape_jkg is not None and record.cape_jkg > 0:
            threshold = self.breach_service.find_applicable_threshold(
                metric_name="cape_jkg",
                disaster_kind="cyclone",
                province=record.province,
                district=record.district,
            )
            
            if threshold:
                severity = self.breach_service.check_breach(
                    value=float(record.cape_jkg),
                    threshold=threshold,
                )
                
                if severity:
                    threshold_value = self.breach_service._get_threshold_value(threshold, severity)
                    breaches.append((True, severity, "cape_jkg", record.cape_jkg, Decimal(str(threshold_value))))
        
        # 7. COLD WAVE - Check minimum temperature
        if record.temp_c is not None:
            threshold = self.breach_service.find_applicable_threshold(
                metric_name="temp_min_c",
                disaster_kind="cold_wave",
                province=record.province,
                district=record.district,
            )
            
            if threshold:
                severity = self.breach_service.check_breach(
                    value=float(record.temp_c),
                    threshold=threshold,
                )
                
                if severity:
                    threshold_value = self.breach_service._get_threshold_value(threshold, severity)
                    breaches.append((True, severity, "temp_min_c", record.temp_c, Decimal(str(threshold_value))))
        
        # 8. DUST STORM - Check wind speed + visibility combination
        if (record.wind_speed_kmh is not None and 
            record.visibility_m is not None and 
            record.wind_speed_kmh >= Decimal("40.0") and 
            record.visibility_m < 1000):
            
            threshold = self.breach_service.find_applicable_threshold(
                metric_name="wind_speed_kmh",
                disaster_kind="dust_storm",
                province=record.province,
                district=record.district,
            )
            
            if threshold:
                severity = self.breach_service.check_breach(
                    value=float(record.wind_speed_kmh),
                    threshold=threshold,
                )
                
                if severity:
                    threshold_value = self.breach_service._get_threshold_value(threshold, severity)
                    breaches.append((True, severity, "wind_speed_kmh", record.wind_speed_kmh, Decimal(str(threshold_value))))
        
        return breaches

    # ── Data Processing ───────────────────────────────────────────

    async def process_location(
        self,
        hourly_records: list[WeatherHourlyWindowBase],
        daily_summaries: list[WeatherDailySummaryBase],
        cycle_id: UUID | None = None,
        data_freshness_minutes: int | None = None,
    ) -> dict[str, int]:
        """Process weather data for a location: check breaches and UPSERT.
        
        Args:
            hourly_records: List of hourly weather records.
            daily_summaries: List of daily weather summaries.
            cycle_id: Unique ID for current collection cycle.
            data_freshness_minutes: Stale data warning threshold.
        
        Returns:
            Dictionary with processing statistics.
        """
        stats = {
            "hourly_upserted": 0,
            "daily_upserted": 0,
            "breaches_detected": 0,
            "errors": 0,
        }
        
        # Process hourly records
        for record in hourly_records:
            try:
                # Assign metadata
                record.cycle_id = cycle_id
                record.data_freshness_minutes = data_freshness_minutes
                
                # Check for ALL breach types
                breaches = await self.check_breaches(record)
                
                if breaches:
                    # Find the most severe breach
                    severity_order = {"extreme": 0, "emergency": 1, "warning": 2, "watch": 3}
                    breaches.sort(key=lambda x: severity_order.get(x[1], 99))
                    
                    # Use the worst breach for the record
                    worst_breach = breaches[0]
                    record.has_breach = worst_breach[0]
                    record.breach_severity = worst_breach[1]
                    record.breach_metric = worst_breach[2]
                    record.breach_observed_value = worst_breach[3]
                    record.breach_threshold_value = worst_breach[4]
                    
                    stats["breaches_detected"] += len(breaches)
                    
                    logger.debug(
                        "Detected %d breach(es) for %s at %s: worst=%s (%s)",
                        len(breaches),
                        record.location_name,
                        record.forecast_for_datetime,
                        worst_breach[2],
                        worst_breach[1],
                    )
                
                # UPSERT to database
                await self.weather_repo.upsert_hourly(record)
                stats["hourly_upserted"] += 1
                
            except Exception as e:
                logger.error("Failed to process hourly record: %s", str(e))
                stats["errors"] += 1
                continue
        
        # Process daily summaries
        for summary in daily_summaries:
            try:
                # Assign metadata
                summary.cycle_id = cycle_id
                summary.data_freshness_minutes = data_freshness_minutes
                
                await self.weather_repo.upsert_daily(summary)
                stats["daily_upserted"] += 1
                
            except Exception as e:
                logger.error("Failed to process daily summary: %s", str(e))
                stats["errors"] += 1
                continue
        
        return stats