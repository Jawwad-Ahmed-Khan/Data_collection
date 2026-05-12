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
from app.core.logger import get_logger

logger = get_logger(__name__)


class WeatherRepository(BaseRepository):
    """Handles persistence of weather data."""

    async def upsert_hourly_batch(self, windows: list[WeatherHourlyWindowBase]) -> int:
        """Bulk insert or update hourly weather windows."""
        if not windows:
            return 0
            
        tuples = [
            (
                w.location_id, w.location_key, w.location_name, w.district, w.province,
                w.latitude, w.longitude, w.forecast_for_datetime,
                w.temp_c, w.temp_apparent_c, w.temp_dewpoint_c, w.precip_mm,
                w.precip_prob_pct, w.rain_mm, w.snowfall_cm, w.snow_depth_m,
                w.precip_3h_mm, w.precip_6h_mm, w.precip_12h_mm, w.precip_24h_mm, w.precip_72h_mm,
                w.wind_speed_kmh, w.wind_gusts_kmh, w.wind_direction_deg,
                w.humidity_pct, w.pressure_hpa, w.visibility_m, w.cloud_cover_pct,
                w.uv_index, w.cape_jkg, w.weather_code, w.weather_description, w.is_daytime,
                w.flag_extreme_heat, w.flag_heatwave, w.flag_heavy_rain, w.flag_very_heavy_rain,
                w.flag_storm, w.flag_severe_storm, w.flag_cold_wave, w.flag_dust_storm,
                w.flag_dense_fog, w.has_breach, w.breach_severity, w.breach_metric,
                w.breach_observed_value, w.breach_threshold_value, w.threshold_id, w.cycle_id
            )
            for w in windows
        ]
        
        try:
            await self.db.execute_many(UPSERT_WEATHER_HOURLY, tuples)
            return len(windows)
        except Exception as e:
            logger.warning("execute_many failed for hourly batch: %s. Falling back to individual inserts.", str(e))
            success_count = 0
            for t in tuples:
                try:
                    await self.db.execute(UPSERT_WEATHER_HOURLY, *t)
                    success_count += 1
                except Exception as row_e:
                    logger.debug("Failed to insert hourly weather row: %s", str(row_e))
            return success_count

    async def upsert_daily_batch(self, summaries: list[WeatherDailySummaryBase]) -> int:
        """Bulk insert or update daily weather summaries."""
        if not summaries:
            return 0
            
        tuples = [
            (
                s.location_id, s.location_key, s.location_name, s.district, s.province,
                s.latitude, s.longitude, s.summary_date,
                s.temp_max_c, s.temp_min_c, s.feels_like_max_c, s.feels_like_min_c,
                s.precip_total_mm, s.precip_prob_max_pct, s.wind_speed_max_kmh,
                s.wind_gusts_max_kmh, s.uv_index_max, s.sunrise_at, s.sunset_at,
                s.dominant_condition, s.flag_extreme_heat_day, s.flag_heatwave_day,
                s.flag_heavy_rain_day, s.flag_storm_day, s.flag_cold_wave_day,
                s.worst_breach_severity, s.cycle_id
            )
            for s in summaries
        ]
        
        try:
            await self.db.execute_many(UPSERT_WEATHER_DAILY, tuples)
            return len(summaries)
        except Exception as e:
            logger.warning("execute_many failed for daily batch: %s. Falling back to individual inserts.", str(e))
            success_count = 0
            for t in tuples:
                try:
                    await self.db.execute(UPSERT_WEATHER_DAILY, *t)
                    success_count += 1
                except Exception as row_e:
                    logger.debug("Failed to insert daily weather row: %s", str(row_e))
            return success_count

    async def upsert_current_weather(self, current: CurrentWeatherLocationBase) -> None:
        """No-op: current_weather_per_location is a VIEW over weather_hourly_window.
        The view is automatically up-to-date once hourly rows are upserted."""
        logger.debug(
            "upsert_current_weather skipped for %s — view is auto-populated from weather_hourly_window",
            current.location_key,
        )

    async def upsert_5day_forecast(self, summary: Weather5DaySummaryBase) -> None:
        """No-op: 5-day data is already stored via upsert_daily_batch to weather_daily_summaries.
        The table weather_5day_forecast_per_location does not exist in the schema."""
        logger.debug(
            "upsert_5day_forecast skipped for %s %s — already stored in weather_daily_summaries",
            summary.location_key,
            summary.summary_date,
        )
