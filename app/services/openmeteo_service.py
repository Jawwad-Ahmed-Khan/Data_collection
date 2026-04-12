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

    async def check_breach(
        self,
        record: WeatherHourlyWindowBase,
    ) -> tuple[bool, str | None, str | None, Decimal | None]:
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
                # Assign metadata
                summary.cycle_id = cycle_id
                summary.data_freshness_minutes = data_freshness_minutes
                
                await self.weather_repo.upsert_daily(summary)
                stats["daily_upserted"] += 1

                # DASHBOARD: Update 5-day forecast view
                # We only take the first 5 days (Open-Meteo returns 5-7 days depending on params)
                if summary.day_offset <= 4:
                    f5day = Weather5DaySummaryBase(
                        location_id=summary.location_id,
                        location_key=summary.location_key,
                        location_name=summary.location_name,
                        district=summary.district,
                        province=summary.province,
                        summary_date=summary.summary_date,
                        day_offset=summary.day_offset,
                        day_label=summary.summary_date.strftime("%a"),
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
                        worst_breach_severity=summary.worst_breach_severity,
                    )
                    await self.weather_repo.upsert_5day_forecast(f5day)

            except Exception as e:
                logger.error("Failed to process daily summary: %s", str(e))
                stats["errors"] += 1
                continue
        
        # DASHBOARD: Update Current Weather View (Identify closest point to now)
        try:
            now = datetime.now(_PKT)
            current_record = None
            min_diff = timedelta(hours=24)

            for record in hourly_records:
                diff = abs((record.forecast_for_datetime - now).total_seconds())
                if diff < min_diff.total_seconds():
                    min_diff = timedelta(seconds=diff)
                    current_record = record
            
            if current_record:
                dashboard_current = CurrentWeatherLocationBase(
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
                    observation_time=current_record.forecast_for_datetime,
                )
                await self.weather_repo.upsert_current_weather(dashboard_current)
                logger.debug(f"Updated dashboard current weather for {current_record.location_name}")
        except Exception as e:
            logger.error(f"Failed to update dashboard current weather: {e}")

        return stats