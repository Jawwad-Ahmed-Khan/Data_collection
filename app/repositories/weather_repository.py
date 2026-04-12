"""
ClimaSync Collection Service — Weather Repository
"""

from datetime import datetime
from uuid import UUID

from app.models.weather_models import (
    WeatherHourlyWindowBase, 
    WeatherDailySummaryBase,
    CurrentWeatherLocationBase,
    Weather5DaySummaryBase
)
from app.repositories.base_repository import BaseRepository
from app.database.queries.weather_queries import (
    UPSERT_WEATHER_HOURLY,
    UPSERT_WEATHER_DAILY,
    UPSERT_CURRENT_WEATHER_PER_LOCATION,
    UPSERT_WEATHER_5DAY_FORECAST,
)


class WeatherRepository(BaseRepository):
    """Handles persistence of weather data."""

    async def upsert_hourly(self, window: WeatherHourlyWindowBase) -> None:
        """Insert or update an hourly weather window."""
        await self.db.execute(
            UPSERT_WEATHER_HOURLY,
            window.location_id,
            window.location_key,
            window.location_name,
            window.district,
            window.province,
            window.latitude,
            window.longitude,
            window.forecast_for_datetime,
            window.forecast_date,
            window.day_offset,
            window.temp_c,
            window.temp_apparent_c,
            window.temp_dewpoint_c,
            window.precip_mm,
            window.precip_prob_pct,
            window.rain_mm,
            window.snowfall_cm,
            window.snow_depth_m,
            window.precip_3h_mm,
            window.precip_6h_mm,
            window.precip_12h_mm,
            window.precip_24h_mm,
            window.precip_72h_mm,
            window.wind_speed_kmh,
            window.wind_gusts_kmh,
            window.wind_direction_deg,
            window.wind_direction_cardinal,
            window.humidity_pct,
            window.pressure_hpa,
            window.visibility_m,
            window.cloud_cover_pct,
            window.uv_index,
            window.cape_jkg,
            window.weather_code,
            window.weather_condition,
            window.weather_description,
            window.is_daytime,
            window.flag_extreme_heat,
            window.flag_heatwave,
            window.flag_heavy_rain,
            window.flag_very_heavy_rain,
            window.flag_storm,
            window.flag_severe_storm,
            window.flag_cold_wave,
            window.flag_dust_storm,
            window.flag_dense_fog,
            window.has_breach,
            window.breach_severity,
            window.breach_metric,
            window.breach_observed_value,
            window.breach_threshold_value,
            window.threshold_id,
            window.cycle_id,
        )

    async def upsert_daily(self, summary: WeatherDailySummaryBase) -> None:
        """Insert or update a daily weather summary."""
        await self.db.execute(
            UPSERT_WEATHER_DAILY,
            summary.location_id,
            summary.location_key,
            summary.location_name,
            summary.district,
            summary.province,
            summary.latitude,
            summary.longitude,
            summary.summary_date,
            summary.day_offset,
            summary.temp_max_c,
            summary.temp_min_c,
            summary.feels_like_max_c,
            summary.feels_like_min_c,
            summary.precip_total_mm,
            summary.precip_prob_max_pct,
            summary.wind_speed_max_kmh,
            summary.wind_gusts_max_kmh,
            summary.uv_index_max,
            summary.sunrise_at,
            summary.sunset_at,
            summary.dominant_condition,
            summary.flag_extreme_heat_day,
            summary.flag_heatwave_day,
            summary.flag_heavy_rain_day,
            summary.flag_storm_day,
            summary.flag_cold_wave_day,
            summary.worst_breach_severity,
            summary.cycle_id,
        )

    async def upsert_current_weather(self, current: CurrentWeatherLocationBase) -> None:
        """Upsert current weather for a location."""
        await self.db.execute(
            UPSERT_CURRENT_WEATHER_PER_LOCATION,
            current.location_id,
            current.location_key,
            current.location_name,
            current.temp_c,
            current.temp_apparent_c,
            current.precip_mm,
            current.wind_speed_kmh,
            current.humidity_pct,
            current.pressure_hpa,
            current.weather_condition,
            current.weather_description,
            current.is_daytime,
            current.observation_time,
        )

    async def upsert_5day_forecast(self, summary: Weather5DaySummaryBase) -> None:
        """Upsert 5-day forecast summary point."""
        await self.db.execute(
            UPSERT_WEATHER_5DAY_FORECAST,
            summary.location_id,
            summary.location_key,
            summary.location_name,
            summary.district,
            summary.province,
            summary.summary_date,
            summary.day_offset,
            summary.day_label,
            summary.temp_max_c,
            summary.temp_min_c,
            summary.feels_like_max_c,
            summary.precip_total_mm,
            summary.precip_prob_max_pct,
            summary.wind_speed_max_kmh,
            summary.wind_gusts_max_kmh,
            summary.uv_index_max,
            summary.dominant_condition,
            summary.sunrise_at,
            summary.sunset_at,
            summary.flag_extreme_heat_day,
            summary.flag_heatwave_day,
            summary.flag_heavy_rain_day,
            summary.flag_storm_day,
            summary.flag_cold_wave_day,
            summary.worst_breach_severity,
        )
