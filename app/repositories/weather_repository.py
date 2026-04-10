"""
ClimaSync Collection Service — Weather Repository
"""

from app.models.weather_models import WeatherHourlyWindowBase, WeatherDailySummaryBase
from app.repositories.base_repository import BaseRepository
from app.database.queries.weather_queries import (
    UPSERT_WEATHER_HOURLY,
    UPSERT_WEATHER_DAILY,
)


class WeatherRepository(BaseRepository):
    """Handles UPSERTing hourly and daily weather observations."""

    async def upsert_hourly(self, weather: WeatherHourlyWindowBase) -> None:
        """Insert or update an hourly weather window record."""
        await self.db.execute(
            UPSERT_WEATHER_HOURLY,
            weather.location_id,
            weather.location_key,
            weather.location_name,
            weather.district,
            weather.province,
            weather.latitude,
            weather.longitude,
            weather.forecast_for_datetime,
            weather.forecast_date,
            weather.day_offset,
            weather.temp_c,
            weather.temp_apparent_c,
            weather.temp_dewpoint_c,
            weather.precip_mm,
            weather.precip_prob_pct,
            weather.precip_24h_mm,
            weather.precip_72h_mm,
            weather.wind_speed_kmh,
            weather.wind_gusts_kmh,
            weather.wind_direction_deg,
            weather.wind_direction_cardinal,
            weather.humidity_pct,
            weather.pressure_hpa,
            weather.visibility_m,
            weather.uv_index,
            weather.cape_jkg,
            weather.weather_code,
            weather.weather_condition,
            weather.weather_description,
            weather.is_daytime,
            weather.flag_extreme_heat,
            weather.flag_heatwave,
            weather.flag_heavy_rain,
            weather.flag_very_heavy_rain,
            weather.flag_storm,
            weather.flag_severe_storm,
            weather.flag_cold_wave,
            weather.flag_dust_storm,
            weather.flag_dense_fog,
            weather.has_breach,
            weather.breach_severity,
            weather.breach_metric,
            weather.breach_observed_value,
        )

    async def upsert_daily(self, summary: WeatherDailySummaryBase) -> None:
        """Insert or update a daily weather summary record."""
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
        )
