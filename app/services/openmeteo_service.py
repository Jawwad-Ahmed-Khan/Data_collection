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

from datetime import datetime, date, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.core.logger import get_logger
from app.models.weather_models import WeatherHourlyWindowBase, WeatherDailySummaryBase
from app.models.reference_models import PakistanLocation
from app.repositories.weather_repository import WeatherRepository
from app.services.breach_service import BreachService

logger = get_logger(__name__)

# Pakistan Standard Time
_PKT = ZoneInfo("Asia/Karachi")


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
            "wind_speed_10m",
            "wind_gusts_10m",
            "wind_direction_10m",
            "relative_humidity_2m",
            "surface_pressure",
            "visibility",
            "uv_index",
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
            "precipitation_probability_max",
            "wind_speed_10m_max",
            "wind_gusts_10m_max",
            "uv_index_max",
            "sunrise",
            "sunset",
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
                temp_c = self._safe_get(hourly_data.get("temperature_2m"), i)
                temp_apparent_c = self._safe_get(hourly_data.get("apparent_temperature"), i)
                temp_dewpoint_c = self._safe_get(hourly_data.get("dew_point_2m"), i)
                precip_mm = self._safe_get(hourly_data.get("precipitation"), i, 0.0)
                precip_prob_pct = self._safe_get(hourly_data.get("precipitation_probability"), i)
                wind_speed_kmh = self._safe_get(hourly_data.get("wind_speed_10m"), i)
                wind_gusts_kmh = self._safe_get(hourly_data.get("wind_gusts_10m"), i)
                wind_direction_deg = self._safe_get(hourly_data.get("wind_direction_10m"), i)
                humidity_pct = self._safe_get(hourly_data.get("relative_humidity_2m"), i)
                pressure_hpa = self._safe_get(hourly_data.get("surface_pressure"), i)
                visibility_m = self._safe_get(hourly_data.get("visibility"), i)
                uv_index = self._safe_get(hourly_data.get("uv_index"), i)
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
                    wind_speed_kmh=wind_speed_kmh,
                    wind_gusts_kmh=wind_gusts_kmh,
                    wind_direction_deg=wind_direction_deg,
                    wind_direction_cardinal=wind_cardinal,
                    humidity_pct=humidity_pct,
                    pressure_hpa=pressure_hpa,
                    visibility_m=visibility_m,
                    uv_index=uv_index,
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
        """Compute rolling precipitation sums (24h, 72h) for each record."""
        for i, record in enumerate(records):
            # 24-hour rolling sum
            precip_24h = 0.0
            for j in range(max(0, i - 23), i + 1):
                precip_24h += records[j].precip_mm
            record.precip_24h_mm = precip_24h
            
            # 72-hour rolling sum
            precip_72h = 0.0
            for j in range(max(0, i - 71), i + 1):
                precip_72h += records[j].precip_mm
            record.precip_72h_mm = precip_72h

    def _set_weather_flags(self, record: WeatherHourlyWindowBase) -> None:
        """Set weather flags based on thresholds."""
        # Extreme heat (>45°C)
        if record.temp_c >= 45.0:
            record.flag_extreme_heat = True
        
        # Heatwave (>40°C)
        if record.temp_c >= 40.0:
            record.flag_heatwave = True
        
        # Heavy rain (>50mm in 24h)
        if record.precip_24h_mm and record.precip_24h_mm >= 50.0:
            record.flag_heavy_rain = True
        
        # Very heavy rain (>100mm in 24h)
        if record.precip_24h_mm and record.precip_24h_mm >= 100.0:
            record.flag_very_heavy_rain = True
        
        # Storm (wind gusts >60 km/h)
        if record.wind_gusts_kmh and record.wind_gusts_kmh >= 60.0:
            record.flag_storm = True
        
        # Severe storm (wind gusts >90 km/h)
        if record.wind_gusts_kmh and record.wind_gusts_kmh >= 90.0:
            record.flag_severe_storm = True
        
        # Cold wave (<5°C)
        if record.temp_c <= 5.0:
            record.flag_cold_wave = True

    def _wind_to_cardinal(self, degrees: int) -> str:
        """Convert wind direction degrees to cardinal direction."""
        directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        index = round(degrees / 45) % 8
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
                temp_max_c = self._safe_get(daily_data.get("temperature_2m_max"), i)
                temp_min_c = self._safe_get(daily_data.get("temperature_2m_min"), i)
                feels_like_max_c = self._safe_get(daily_data.get("apparent_temperature_max"), i)
                feels_like_min_c = self._safe_get(daily_data.get("apparent_temperature_min"), i)
                precip_total_mm = self._safe_get(daily_data.get("precipitation_sum"), i, 0.0)
                precip_prob_max_pct = self._safe_get(daily_data.get("precipitation_probability_max"), i)
                wind_speed_max_kmh = self._safe_get(daily_data.get("wind_speed_10m_max"), i)
                wind_gusts_max_kmh = self._safe_get(daily_data.get("wind_gusts_10m_max"), i)
                uv_index_max = self._safe_get(daily_data.get("uv_index_max"), i)
                
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
                    precip_prob_max_pct=precip_prob_max_pct,
                    wind_speed_max_kmh=wind_speed_max_kmh,
                    wind_gusts_max_kmh=wind_gusts_max_kmh,
                    uv_index_max=uv_index_max,
                    sunrise_at=sunrise_at,
                    sunset_at=sunset_at,
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
        if summary.temp_max_c >= 45.0:
            summary.flag_extreme_heat_day = True
        
        if summary.temp_max_c >= 40.0:
            summary.flag_heatwave_day = True
        
        if summary.precip_total_mm >= 50.0:
            summary.flag_heavy_rain_day = True
        
        if summary.wind_gusts_max_kmh and summary.wind_gusts_max_kmh >= 60.0:
            summary.flag_storm_day = True
        
        if summary.temp_min_c <= 5.0:
            summary.flag_cold_wave_day = True

    # ── Breach Detection ──────────────────────────────────────────

    async def check_breach(
        self,
        record: WeatherHourlyWindowBase,
    ) -> tuple[bool, str | None, str | None, float | None]:
        """Check if weather metrics cross thresholds.
        
        Args:
            record: Hourly weather record.
        
        Returns:
            Tuple of (has_breach, severity, metric_name, observed_value).
        """
        # Check temperature thresholds
        threshold = self.breach_service.find_applicable_threshold(
            metric_name="temp_max_c",
            disaster_kind="heatwave",
            province=record.province,
            district=record.district,
        )
        
        if threshold:
            severity = self.breach_service.check_breach(
                value=record.temp_c,
                threshold=threshold,
            )
            
            if severity:
                await self.breach_service.create_breach(
                    source_api="open_meteo",
                    disaster_kind="heatwave",
                    metric_name="temp_max_c",
                    observed_value=record.temp_c,
                    threshold=threshold,
                    severity=severity,
                    observation_time=record.forecast_for_datetime,
                    location_name=record.location_name,
                    district=record.district,
                    province=record.province,
                    latitude=record.latitude,
                    longitude=record.longitude,
                    weather_location_id=record.location_id,
                    is_forecast_breach=True,
                    forecast_horizon_h=record.day_offset * 24,
                )
                
                return True, severity, "temp_max_c", record.temp_c
        
        return False, None, None, None

    # ── Data Processing ───────────────────────────────────────────

    async def process_location(
        self,
        hourly_records: list[WeatherHourlyWindowBase],
        daily_summaries: list[WeatherDailySummaryBase],
    ) -> dict[str, int]:
        """Process weather data for a location: check breaches and UPSERT.
        
        Args:
            hourly_records: List of hourly weather records.
            daily_summaries: List of daily weather summaries.
        
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
                # Check for breach
                has_breach, severity, metric, value = await self.check_breach(record)
                record.has_breach = has_breach
                record.breach_severity = severity
                record.breach_metric = metric
                record.breach_observed_value = value
                
                if has_breach:
                    stats["breaches_detected"] += 1
                
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
                await self.weather_repo.upsert_daily(summary)
                stats["daily_upserted"] += 1
            except Exception as e:
                logger.error("Failed to process daily summary: %s", str(e))
                stats["errors"] += 1
                continue
        
        return stats
