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
            "pressure_msl",
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
            "wind_speed_unit": "kmh",
            "precipitation_unit": "mm",
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
            "pressure_msl",
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
            "wind_speed_unit": "kmh",
            "precipitation_unit": "mm",
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
            "wind_speed_unit": "kmh",
            "precipitation_unit": "mm",
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
            
        if len(times) != 120:
            logger.warning("Expected 120 hourly records for %s, got %d", location.location_name, len(times))
        
        records = []
        
        for i, time_str in enumerate(times):
            try:
                from datetime import timezone
                # Parse timestamp and convert local PKT to UTC
                naive_dt = datetime.fromisoformat(time_str)
                pkt_dt = naive_dt.replace(tzinfo=_PKT)
                utc_dt = pkt_dt.astimezone(timezone.utc)
                forecast_date = pkt_dt.date()
                
                # Calculate day offset
                today = datetime.now(_PKT).date()
                day_offset = (forecast_date - today).days
                
                # Extract values (with safe indexing)
                # double precision columns: strictly preserve None if missing
                temp_c = to_decimal(self._safe_get(hourly_data.get("temperature_2m"), i))
                temp_apparent_c = to_decimal(self._safe_get(hourly_data.get("apparent_temperature"), i))
                temp_dewpoint_c = to_decimal(self._safe_get(hourly_data.get("dew_point_2m"), i))
                precip_mm = to_decimal(self._safe_get(hourly_data.get("precipitation"), i))
                rain_mm = to_decimal(self._safe_get(hourly_data.get("rain"), i))
                snowfall_cm = to_decimal(self._safe_get(hourly_data.get("snowfall"), i))
                snow_depth_m = to_decimal(self._safe_get(hourly_data.get("snow_depth"), i))
                wind_speed_kmh = to_decimal(self._safe_get(hourly_data.get("wind_speed_10m"), i))
                wind_gusts_kmh = to_decimal(self._safe_get(hourly_data.get("wind_gusts_10m"), i))
                pressure_hpa = to_decimal(self._safe_get(hourly_data.get("pressure_msl"), i))
                uv_index = to_decimal(self._safe_get(hourly_data.get("uv_index"), i))
                cape_jkg = to_decimal(self._safe_get(hourly_data.get("cape"), i))
                
                # SMALLINT/INT columns: convert and clamp safely
                raw_prob = self._safe_get(hourly_data.get("precipitation_probability"), i)
                precip_prob_pct = max(0, min(100, int(raw_prob))) if raw_prob is not None else None
                
                raw_dir = self._safe_get(hourly_data.get("wind_direction_10m"), i)
                wind_direction_deg = int(raw_dir) if raw_dir is not None else None
                
                raw_hum = self._safe_get(hourly_data.get("relative_humidity_2m"), i)
                humidity_pct = max(0, min(100, int(raw_hum))) if raw_hum is not None else None
                
                raw_vis = self._safe_get(hourly_data.get("visibility"), i)
                visibility_m = int(raw_vis) if raw_vis is not None else None
                
                raw_cloud = self._safe_get(hourly_data.get("cloud_cover"), i)
                cloud_cover_pct = max(0, min(100, int(raw_cloud))) if raw_cloud is not None else None
                
                raw_code = self._safe_get(hourly_data.get("weather_code"), i)
                weather_code = int(raw_code) if raw_code is not None else None
                
                raw_day = self._safe_get(hourly_data.get("is_day"), i)
                is_daytime = bool(int(raw_day)) if raw_day is not None else None
                
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
                    forecast_for_datetime=utc_dt,
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
        
        # Compute rolling sums from API array
        precip_array = hourly_data.get("precipitation", [])
        self._compute_rolling_sums(records, precip_array)
        
        # Set weather flags
        for record in records:
            self._set_weather_flags(record)
            
        # Filter strictly to 0-4 days (5-day window)
        future_records = [r for r in records if 0 <= r.day_offset <= 4]
        
        logger.info("Parsed %d hourly records for %s", len(future_records), location.location_name)
        return future_records

    def _safe_get(self, array: list | None, index: int, default: Any = None) -> Any:
        """Safely get value from array at index."""
        if array is None or index >= len(array):
            return default
        value = array[index]
        return value if value is not None else default

    def _compute_rolling_sums(self, records: list[WeatherHourlyWindowBase], precip_array: list[Any]) -> None:
        """Compute rolling precipitation sums directly from the API array."""
        # Convert API array to a list of floats (or None)
        precip_floats = []
        for p in precip_array:
            try:
                precip_floats.append(float(p) if p is not None else None)
            except (ValueError, TypeError):
                precip_floats.append(None)
                
        # Ensure it has enough elements to match records
        while len(precip_floats) < len(records):
            precip_floats.append(None)

        for i, record in enumerate(records):
            def get_rolling_sum(window_size: int) -> Decimal | None:
                start_idx = max(0, i - window_size + 1)
                window = precip_floats[start_idx : i + 1]
                
                # If ALL elements in the window are None, return None
                if all(val is None for val in window):
                    return None
                    
                # Replace None with 0.0 for accumulation
                total = sum(val if val is not None else 0.0 for val in window)
                return Decimal(str(round(total, 3)))

            record.precip_3h_mm = get_rolling_sum(3)
            record.precip_6h_mm = get_rolling_sum(6)
            record.precip_12h_mm = get_rolling_sum(12)
            record.precip_24h_mm = get_rolling_sum(24)
            record.precip_72h_mm = get_rolling_sum(72)

    def _set_weather_flags(self, record: WeatherHourlyWindowBase) -> None:
        """Set weather flags based on strict thresholds."""
        # Extreme heat: temp_apparent_c >= 47.0 OR temp_c >= 45.0
        if (record.temp_apparent_c is not None and record.temp_apparent_c >= Decimal("47.0")) or \
           (record.temp_c is not None and record.temp_c >= Decimal("45.0")):
            record.flag_extreme_heat = True
        
        # Heatwave: temp_c >= 40.0
        if record.temp_c is not None and record.temp_c >= Decimal("40.0"):
            record.flag_heatwave = True
        
        # Heavy rain: precip_mm >= 15.0 OR precip_24h_mm >= 50.0
        if (record.precip_mm is not None and record.precip_mm >= Decimal("15.0")) or \
           (record.precip_24h_mm is not None and record.precip_24h_mm >= Decimal("50.0")):
            record.flag_heavy_rain = True
        
        # Very heavy rain: precip_mm >= 25.0 OR precip_24h_mm >= 100.0
        if (record.precip_mm is not None and record.precip_mm >= Decimal("25.0")) or \
           (record.precip_24h_mm is not None and record.precip_24h_mm >= Decimal("100.0")):
            record.flag_very_heavy_rain = True
        
        # Storm: weather_code in (95, 96, 99) OR (cape_jkg >= 1000 and weather_code >= 80)
        is_storm_code = record.weather_code in (95, 96, 99)
        high_cape_storm = (record.cape_jkg is not None and record.cape_jkg >= Decimal("1000.0") and 
                           record.weather_code is not None and record.weather_code >= 80)
        if is_storm_code or high_cape_storm:
            record.flag_storm = True
        
        # Severe storm: weather_code in (96, 99) OR (cape_jkg >= 2500)
        if record.weather_code in (96, 99) or (record.cape_jkg is not None and record.cape_jkg >= Decimal("2500.0")):
            record.flag_severe_storm = True
        
        # Cold wave: gilgit_baltistan/azad_kashmir <= -5.0, others <= 0.0
        if record.temp_c is not None:
            if record.province in ('gilgit_baltistan', 'azad_kashmir') and record.temp_c <= Decimal("-5.0"):
                record.flag_cold_wave = True
            elif record.province not in ('gilgit_baltistan', 'azad_kashmir') and record.temp_c <= Decimal("0.0"):
                record.flag_cold_wave = True
        
        # Dust storm: wind_gusts >= 62 AND humidity <= 20 AND province in ('balochistan', 'sindh', 'punjab')
        if (record.wind_gusts_kmh is not None and record.wind_gusts_kmh >= Decimal("62.0") and
            record.humidity_pct is not None and record.humidity_pct <= 20 and
            record.province in ('balochistan', 'sindh', 'punjab')):
            record.flag_dust_storm = True
        
        # Dense fog: weather_code in (45, 48) AND visibility_m < 200
        if record.weather_code in (45, 48) and record.visibility_m is not None and record.visibility_m < 200:
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
            
        if len(times) != 5:
            logger.warning("Expected 5 daily records for %s, got %d", location.location_name, len(times))
        
        summaries = []
        today = datetime.now(_PKT).date()
        
        for i, time_str in enumerate(times):
            try:
                summary_date = date.fromisoformat(time_str)
                day_offset = (summary_date - today).days
                
                # Extract values
                # double precision columns: convert to float safely preserving None
                temp_max_c = to_decimal(self._safe_get(daily_data.get("temperature_2m_max"), i))
                temp_min_c = to_decimal(self._safe_get(daily_data.get("temperature_2m_min"), i))
                feels_like_max_c = to_decimal(self._safe_get(daily_data.get("apparent_temperature_max"), i))
                feels_like_min_c = to_decimal(self._safe_get(daily_data.get("apparent_temperature_min"), i))
                
                precip_total_mm = to_decimal(self._safe_get(daily_data.get("precipitation_sum"), i))
                rain_total_mm = to_decimal(self._safe_get(daily_data.get("rain_sum"), i))
                snowfall_total_cm = to_decimal(self._safe_get(daily_data.get("snowfall_sum"), i))
                raw_precip_hours = self._safe_get(daily_data.get("precipitation_hours"), i)
                precip_hours = int(raw_precip_hours) if raw_precip_hours is not None else None
                
                raw_prob_max = self._safe_get(daily_data.get("precipitation_probability_max"), i)
                precip_prob_max_pct = max(0, min(100, int(raw_prob_max))) if raw_prob_max is not None else None
                
                wind_speed_max_kmh = to_decimal(self._safe_get(daily_data.get("wind_speed_10m_max"), i))
                wind_gusts_max_kmh = to_decimal(self._safe_get(daily_data.get("wind_gusts_10m_max"), i))
                
                raw_wind_dir = self._safe_get(daily_data.get("wind_direction_10m_dominant"), i)
                wind_dir_dominant = int(raw_wind_dir) if raw_wind_dir is not None else None
                
                uv_index_max = to_decimal(self._safe_get(daily_data.get("uv_index_max"), i))
                
                # Day Overview
                raw_code_daily = self._safe_get(daily_data.get("weather_code"), i)
                weather_code_daily = int(raw_code_daily) if raw_code_daily is not None else None
                dominant_condition, _ = self._decode_weather_code(weather_code_daily)
                
                # daylight_duration is in seconds, convert to hours
                daylight_duration_s = to_decimal(self._safe_get(daily_data.get("daylight_duration"), i))
                daylight_hours = (daylight_duration_s / Decimal("3600.0")).quantize(Decimal("0.01")) if daylight_duration_s is not None else None

                # Parse sunrise/sunset and convert to UTC
                from datetime import timezone
                sunrise_str = self._safe_get(daily_data.get("sunrise"), i)
                sunset_str = self._safe_get(daily_data.get("sunset"), i)
                sunrise_at = datetime.fromisoformat(sunrise_str).replace(tzinfo=_PKT).astimezone(timezone.utc) if sunrise_str else None
                sunset_at = datetime.fromisoformat(sunset_str).replace(tzinfo=_PKT).astimezone(timezone.utc) if sunset_str else None
                
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
        
        # Filter strictly to 0-4 days
        future_summaries = [s for s in summaries if 0 <= s.day_offset <= 4]
        
        logger.info("Parsed %d daily summaries for %s", len(future_summaries), location.location_name)
        return future_summaries

    def _set_daily_flags(self, summary: WeatherDailySummaryBase) -> None:
        """Set daily weather flags based on thresholds."""
        if summary.temp_max_c is not None and summary.temp_max_c >= Decimal("45.0"):
            summary.flag_extreme_heat_day = True
        
        if summary.temp_max_c is not None and summary.temp_max_c >= Decimal("40.0"):
            summary.flag_heatwave_day = True
        
        if summary.precip_total_mm is not None and summary.precip_total_mm >= Decimal("50.0"):
            summary.flag_heavy_rain_day = True
        
        if summary.weather_code_dominant in (95, 96, 99):
            summary.flag_storm_day = True
        
        if summary.temp_min_c is not None and summary.temp_min_c <= Decimal("-5.0"):
            summary.flag_cold_wave_day = True

    # ── Breach Detection ──────────────────────────────────────────

    async def check_breaches(
        self,
        record: WeatherHourlyWindowBase,
        suppressed_metrics: set[str],
    ) -> list[tuple[bool, str | None, str | None, Decimal | None, Decimal | None]]:
        """Check if weather metrics cross thresholds and create breaches.
        
        Args:
            record: Hourly weather record.
            suppressed_metrics: Set of metric names already breached in this location's cycle.
        
        Returns:
            List of tuples: (has_breach, severity, metric_name, observed_value, threshold_value)
        """
        breaches = []
        
        from datetime import timezone
        now_utc = datetime.now(timezone.utc)
        is_forecast = record.forecast_for_datetime > now_utc
        horizon_s = (record.forecast_for_datetime - now_utc).total_seconds()
        forecast_horizon_h = max(0, round(horizon_s / 3600))
        
        async def _evaluate_metric(metric_name: str, disaster_kind: str, value: Decimal | None):
            if value is None:
                return
            if metric_name not in ["temp_max_c", "temp_min_c", "temp_c"] and value <= 0:
                return
            if metric_name in suppressed_metrics:
                return
                
            threshold = self.breach_service.find_applicable_threshold(
                metric_name=metric_name,
                disaster_kind=disaster_kind,
                province=record.province,
                district=record.district,
            )
            
            if threshold:
                severity = self.breach_service.check_breach(
                    value=float(value),
                    threshold=threshold,
                )
                
                if severity:
                    threshold_value = self.breach_service._get_threshold_value(threshold, severity)
                    breaches.append((True, severity, metric_name, value, Decimal(str(threshold_value))))
                    
                    await self.breach_service.create_breach(
                        source_api="open_meteo",
                        disaster_kind=disaster_kind,
                        metric_name=metric_name,
                        observed_value=float(value),
                        threshold=threshold,
                        severity=severity,
                        observation_time=record.forecast_for_datetime,
                        location_name=record.location_name,
                        district=record.district,
                        province=record.province,
                        latitude=record.latitude,
                        longitude=record.longitude,
                        weather_location_id=record.location_id,
                        is_forecast_breach=is_forecast,
                        forecast_horizon_h=forecast_horizon_h,
                    )
                    
                    suppressed_metrics.add(metric_name)

        await _evaluate_metric("temp_max_c", "heatwave", record.temp_c)
        await _evaluate_metric("precip_1h_mm", "heavy_rain", record.precip_mm)
        await _evaluate_metric("precip_24h_mm", "heavy_rain", record.precip_24h_mm)
        await _evaluate_metric("precip_72h_mm", "flash_flood", record.precip_72h_mm)
        await _evaluate_metric("wind_gusts_kmh", "cyclone", record.wind_gusts_kmh)
        await _evaluate_metric("cape_jkg", "cyclone", record.cape_jkg)
        await _evaluate_metric("temp_min_c", "cold_wave", record.temp_c)
        
        if (record.wind_speed_kmh is not None and 
            record.visibility_m is not None and 
            record.wind_speed_kmh >= Decimal("40.0") and 
            record.visibility_m < 1000):
            await _evaluate_metric("wind_speed_kmh", "dust_storm", record.wind_speed_kmh)

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
        
        # Track breached metrics per location to suppress duplicates in the 120h loop
        suppressed_metrics: set[str] = set()
        
        # Track daily worst severity (day_offset -> severity_str)
        daily_worst_severity: dict[int, str] = {}
        severity_order = {"extreme": 0, "emergency": 1, "warning": 2, "watch": 3}
        
        # Process hourly records
        for record in hourly_records:
            try:
                # Assign metadata
                record.cycle_id = cycle_id
                record.data_freshness_minutes = data_freshness_minutes
                
                # Check for ALL breach types
                breaches = await self.check_breaches(record, suppressed_metrics)
                
                if breaches:
                    # Find the most severe breach
                    breaches.sort(key=lambda x: severity_order.get(x[1], 99))
                    
                    # Use the worst breach for the record
                    worst_breach = breaches[0]
                    record.has_breach = worst_breach[0]
                    record.breach_severity = worst_breach[1]
                    record.breach_metric = worst_breach[2]
                    record.breach_observed_value = worst_breach[3]
                    record.breach_threshold_value = worst_breach[4]
                    
                    stats["breaches_detected"] += len(breaches)
                    
                    # Update daily worst severity
                    if record.day_offset is not None and record.breach_severity:
                        current_worst = daily_worst_severity.get(record.day_offset)
                        if current_worst is None or severity_order.get(record.breach_severity, 99) < severity_order.get(current_worst, 99):
                            daily_worst_severity[record.day_offset] = record.breach_severity
                    
                    logger.debug(
                        "Detected %d breach(es) for %s at %s: worst=%s (%s)",
                        len(breaches),
                        record.location_name,
                        record.forecast_for_datetime,
                        worst_breach[2],
                        worst_breach[1],
                    )
                
            except Exception as e:
                logger.error("Failed to process hourly record: %s", str(e))
                stats["errors"] += 1
                continue
                
        # Batch UPSERT to database
        if hourly_records:
            try:
                upserted = await self.weather_repo.upsert_hourly_batch(hourly_records)
                stats["hourly_upserted"] += upserted
            except Exception as e:
                logger.error("Failed to batch upsert hourly records: %s", str(e))
                stats["errors"] += len(hourly_records)
        
        # Process daily summaries
        for summary in daily_summaries:
            try:
                # Assign metadata
                summary.cycle_id = cycle_id
                summary.data_freshness_minutes = data_freshness_minutes
                
                # Assign worst hourly severity for this day
                if summary.day_offset in daily_worst_severity:
                    summary.worst_breach_severity = daily_worst_severity[summary.day_offset]
            except Exception as e:
                logger.error("Failed to process daily summary metadata: %s", str(e))
                continue
                
        # Batch UPSERT daily summaries
        if daily_summaries:
            try:
                upserted = await self.weather_repo.upsert_daily_batch(daily_summaries)
                stats["daily_upserted"] += upserted
            except Exception as e:
                logger.error("Failed to batch upsert daily summaries: %s", str(e))
                stats["errors"] += len(daily_summaries)
                
        # Upsert 5-day forecast representation
        for summary in daily_summaries:
            try:
                day_label = summary.summary_date.strftime("%a") if summary.day_offset > 1 else ("Tomorrow" if summary.day_offset == 1 else "Today")
                forecast_5d = Weather5DaySummaryBase(
                    location_id=summary.location_id,
                    location_key=summary.location_key,
                    location_name=summary.location_name,
                    district=summary.district,
                    province=summary.province,
                    summary_date=summary.summary_date,
                    day_offset=summary.day_offset,
                    day_label=day_label,
                    temp_max_c=summary.temp_max_c,
                    temp_min_c=summary.temp_min_c,
                    feels_like_max_c=summary.feels_like_max_c,
                    precip_total_mm=summary.precip_total_mm,
                    precip_prob_max_pct=summary.precip_prob_max_pct,
                    wind_speed_max_kmh=summary.wind_speed_max_kmh,
                    wind_gusts_max_kmh=summary.wind_gusts_max_kmh,
                    uv_index_max=summary.uv_index_max,
                    dominant_condition=summary.dominant_condition,
                    sunrise_at=summary.sunrise_at,
                    sunset_at=summary.sunset_at,
                    flag_extreme_heat_day=summary.flag_extreme_heat_day,
                    flag_heatwave_day=summary.flag_heatwave_day,
                    flag_heavy_rain_day=summary.flag_heavy_rain_day,
                    flag_storm_day=summary.flag_storm_day,
                    flag_cold_wave_day=summary.flag_cold_wave_day,
                    worst_breach_severity=summary.worst_breach_severity
                )
                await self.weather_repo.upsert_5day_forecast(forecast_5d)
                
            except Exception as e:
                logger.error("Failed to process 5-day forecast: %s", str(e))
                stats["errors"] += 1
                continue
                
        # Find current hour and upsert current weather
        now = datetime.now(_PKT)
        current_record = None
        min_diff = float('inf')
        for record in hourly_records:
            if record.day_offset >= 0:
                diff = abs((record.forecast_for_datetime - now).total_seconds())
                if diff < min_diff:
                    min_diff = diff
                    current_record = record
                    
        if current_record:
            try:
                current_weather = CurrentWeatherLocationBase(
                    location_id=current_record.location_id,
                    location_key=current_record.location_key,
                    location_name=current_record.location_name,
                    temp_c=current_record.temp_c,
                    temp_apparent_c=current_record.temp_apparent_c,
                    precip_mm=current_record.precip_mm,
                    wind_speed_kmh=current_record.wind_speed_kmh,
                    humidity_pct=current_record.humidity_pct,
                    pressure_hpa=current_record.pressure_hpa,
                    weather_condition=current_record.weather_condition,
                    weather_description=current_record.weather_description,
                    is_daytime=current_record.is_daytime,
                    observation_time=now,
                    data_age_minutes=data_freshness_minutes,
                    data_freshness="fresh" if data_freshness_minutes is not None and data_freshness_minutes < 120 else "stale"
                )
                await self.weather_repo.upsert_current_weather(current_weather)
            except Exception as e:
                logger.error("Failed to upsert current weather: %s", str(e))
                stats["errors"] += 1
        
        return stats