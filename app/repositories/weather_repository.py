"""
ClimaSync Collection Service — Weather Repository

Strictly aligned with the provided database schema to fix parameter mismatch errors.
"""

from decimal import Decimal
from uuid import UUID
from datetime import datetime
from app.models.weather_models import WeatherHourlyWindowBase, WeatherDailySummaryBase
from app.repositories.base_repository import BaseRepository
import logging

logger = logging.getLogger(__name__)

class WeatherRepository(BaseRepository):
    """Handles UPSERTing hourly and daily weather observations."""

    async def upsert_hourly(self, weather: WeatherHourlyWindowBase) -> None:
        """Insert or update an hourly weather window record."""
        # 56 Columns in total per schema. 
        # We skip last_updated_at in INSERT (it has default and updated in SET).
        # We handle coordinates separately with ST_SetSRID.
        
        query = """
            INSERT INTO weather_hourly_window (
                location_id, forecast_for_datetime, forecast_date, day_offset,
                location_key, location_name, district, province,
                latitude, longitude, coordinates, cycle_id, data_freshness_minutes,
                temp_c, temp_apparent_c, temp_dewpoint_c, precip_mm,
                precip_prob_pct, rain_mm, snowfall_cm, snow_depth_m,
                precip_3h_mm, precip_6h_mm, precip_12h_mm, precip_24h_mm, precip_72h_mm,
                wind_speed_kmh, wind_gusts_kmh, wind_direction_deg,
                wind_direction_cardinal, humidity_pct, pressure_hpa,
                visibility_m, cloud_cover_pct, uv_index, cape_jkg,
                weather_code, weather_condition, weather_description,
                is_daytime, flag_extreme_heat, flag_heatwave,
                flag_heavy_rain, flag_very_heavy_rain, flag_storm,
                flag_severe_storm, flag_cold_wave, flag_dust_storm,
                flag_dense_fog, has_breach, breach_severity,
                breach_metric, breach_observed_value, breach_threshold_value,
                threshold_id
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8,
                $9::numeric, $10::numeric, ST_SetSRID(ST_MakePoint($10::float8, $9::float8), 4326),
                $11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
                $21, $22, $23, $24, $25, $26, $27, $28, $29, $30,
                $31, $32, $33, $34, $35, $36, $37, $38, $39,
                $40, $41, $42, $43, $44, $45, $46, $47, $48,
                $49, $50, $51, $52, $53, $54
            )
            ON CONFLICT (location_id, forecast_for_datetime) DO UPDATE SET
                temp_c = EXCLUDED.temp_c,
                temp_apparent_c = EXCLUDED.temp_apparent_c,
                temp_dewpoint_c = EXCLUDED.temp_dewpoint_c,
                precip_mm = EXCLUDED.precip_mm,
                precip_prob_pct = EXCLUDED.precip_prob_pct,
                rain_mm = EXCLUDED.rain_mm,
                snowfall_cm = EXCLUDED.snowfall_cm,
                snow_depth_m = EXCLUDED.snow_depth_m,
                precip_3h_mm = EXCLUDED.precip_3h_mm,
                precip_6h_mm = EXCLUDED.precip_6h_mm,
                precip_12h_mm = EXCLUDED.precip_12h_mm,
                precip_24h_mm = EXCLUDED.precip_24h_mm,
                precip_72h_mm = EXCLUDED.precip_72h_mm,
                wind_speed_kmh = EXCLUDED.wind_speed_kmh,
                wind_gusts_kmh = EXCLUDED.wind_gusts_kmh,
                wind_direction_deg = EXCLUDED.wind_direction_deg,
                wind_direction_cardinal = EXCLUDED.wind_direction_cardinal,
                humidity_pct = EXCLUDED.humidity_pct,
                pressure_hpa = EXCLUDED.pressure_hpa,
                visibility_m = EXCLUDED.visibility_m,
                cloud_cover_pct = EXCLUDED.cloud_cover_pct,
                uv_index = EXCLUDED.uv_index,
                cape_jkg = EXCLUDED.cape_jkg,
                weather_code = EXCLUDED.weather_code,
                weather_condition = EXCLUDED.weather_condition,
                weather_description = EXCLUDED.weather_description,
                is_daytime = EXCLUDED.is_daytime,
                flag_extreme_heat = EXCLUDED.flag_extreme_heat,
                flag_heatwave = EXCLUDED.flag_heatwave,
                flag_heavy_rain = EXCLUDED.flag_heavy_rain,
                flag_very_heavy_rain = EXCLUDED.flag_very_heavy_rain,
                flag_storm = EXCLUDED.flag_storm,
                flag_severe_storm = EXCLUDED.flag_severe_storm,
                flag_cold_wave = EXCLUDED.flag_cold_wave,
                flag_dust_storm = EXCLUDED.flag_dust_storm,
                flag_dense_fog = EXCLUDED.flag_dense_fog,
                has_breach = EXCLUDED.has_breach,
                breach_severity = EXCLUDED.breach_severity,
                breach_metric = EXCLUDED.breach_metric,
                breach_observed_value = EXCLUDED.breach_observed_value,
                breach_threshold_value = EXCLUDED.breach_threshold_value,
                threshold_id = EXCLUDED.threshold_id,
                cycle_id = EXCLUDED.cycle_id,
                last_updated_at = now()
        """
        
        await self.db.execute(
            query,
            weather.location_id,           # $1
            weather.forecast_for_datetime, # $2
            weather.forecast_date,         # $3
            weather.day_offset,            # $4
            weather.location_key,          # $5
            weather.location_name,         # $6
            weather.district,              # $7
            weather.province,              # $8
            weather.latitude,              # $9
            weather.longitude,             # $10
            weather.cycle_id,              # $11
            weather.data_freshness_minutes, # $12
            weather.temp_c,                # $13
            weather.temp_apparent_c,       # $14
            weather.temp_dewpoint_c,       # $15
            weather.precip_mm,             # $16
            weather.precip_prob_pct,       # $17
            weather.rain_mm,               # $18
            weather.snowfall_cm,           # $19
            weather.snow_depth_m,          # $20
            weather.precip_3h_mm,          # $21
            weather.precip_6h_mm,          # $22
            weather.precip_12h_mm,         # $23
            weather.precip_24h_mm,         # $24
            weather.precip_72h_mm,         # $25
            weather.wind_speed_kmh,        # $26
            weather.wind_gusts_kmh,        # $27
            weather.wind_direction_deg,    # $28
            weather.wind_direction_cardinal, # $29
            weather.humidity_pct,          # $30
            weather.pressure_hpa,          # $31
            weather.visibility_m,          # $32
            weather.cloud_cover_pct,       # $33
            weather.uv_index,              # $34
            weather.cape_jkg,              # $35
            weather.weather_code,          # $36
            weather.weather_condition,     # $37
            weather.weather_description,   # $38
            weather.is_daytime,            # $39
            weather.flag_extreme_heat,     # $40
            weather.flag_heatwave,         # $41
            weather.flag_heavy_rain,       # $42
            weather.flag_very_heavy_rain,  # $43
            weather.flag_storm,            # $44
            weather.flag_severe_storm,     # $45
            weather.flag_cold_wave,        # $46
            weather.flag_dust_storm,       # $47
            weather.flag_dense_fog,        # $48
            weather.has_breach,            # $49
            weather.breach_severity,       # $50
            weather.breach_metric,         # $51
            weather.breach_observed_value, # $52
            weather.breach_threshold_value, # $53
            weather.threshold_id           # $54
        )

    async def upsert_daily(self, summary: WeatherDailySummaryBase) -> None:
        """Insert or update a daily weather summary record."""
        # 36 Columns in schema. Skipping last_updated_at in INSERT.
        
        query = """
            INSERT INTO weather_daily_summaries (
                location_id, summary_date, day_offset, location_key,
                location_name, district, province, latitude, longitude,
                coordinates, cycle_id, temp_max_c, temp_min_c,
                feels_like_max_c, feels_like_min_c, precip_total_mm,
                rain_total_mm, snowfall_total_cm, precip_hours,
                precip_prob_max_pct, wind_speed_max_kmh, wind_gusts_max_kmh,
                wind_dominant_cardinal, dominant_condition, weather_code_dominant,
                uv_index_max, sunrise_at, sunset_at, daylight_hours,
                flag_extreme_heat_day, flag_heatwave_day, flag_heavy_rain_day,
                flag_storm_day, flag_cold_wave_day, worst_breach_severity
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8::numeric, $9::numeric,
                ST_SetSRID(ST_MakePoint($9::float8, $8::float8), 4326),
                $10, $11, $12, $13, $14, $15, $16, $17, $18, 
                $19, $20, $21, $22, $23, $24, $25, $26, $27, $28,
                $29, $30, $31, $32, $33, $34
            )
            ON CONFLICT (location_id, summary_date) DO UPDATE SET
                temp_max_c = EXCLUDED.temp_max_c,
                temp_min_c = EXCLUDED.temp_min_c,
                feels_like_max_c = EXCLUDED.feels_like_max_c,
                feels_like_min_c = EXCLUDED.feels_like_min_c,
                precip_total_mm = EXCLUDED.precip_total_mm,
                rain_total_mm = EXCLUDED.rain_total_mm,
                snowfall_total_cm = EXCLUDED.snowfall_total_cm,
                precip_hours = EXCLUDED.precip_hours,
                precip_prob_max_pct = EXCLUDED.precip_prob_max_pct,
                wind_speed_max_kmh = EXCLUDED.wind_speed_max_kmh,
                wind_gusts_max_kmh = EXCLUDED.wind_gusts_max_kmh,
                wind_dominant_cardinal = EXCLUDED.wind_dominant_cardinal,
                uv_index_max = EXCLUDED.uv_index_max,
                sunrise_at = EXCLUDED.sunrise_at,
                sunset_at = EXCLUDED.sunset_at,
                daylight_hours = EXCLUDED.daylight_hours,
                dominant_condition = EXCLUDED.dominant_condition,
                weather_code_dominant = EXCLUDED.weather_code_dominant,
                flag_extreme_heat_day = EXCLUDED.flag_extreme_heat_day,
                flag_heatwave_day = EXCLUDED.flag_heatwave_day,
                flag_heavy_rain_day = EXCLUDED.flag_heavy_rain_day,
                flag_storm_day = EXCLUDED.flag_storm_day,
                flag_cold_wave_day = EXCLUDED.flag_cold_wave_day,
                worst_breach_severity = EXCLUDED.worst_breach_severity,
                cycle_id = EXCLUDED.cycle_id,
                last_updated_at = now()
        """
        
        await self.db.execute(
            query,
            summary.location_id,           # $1
            summary.summary_date,          # $2
            summary.day_offset,            # $3
            summary.location_key,          # $4
            summary.location_name,         # $5
            summary.district,              # $6
            summary.province,              # $7
            summary.latitude,              # $8
            summary.longitude,             # $9
            summary.cycle_id,              # $10
            summary.temp_max_c,            # $11
            summary.temp_min_c,            # $12
            summary.feels_like_max_c,      # $13
            summary.feels_like_min_c,      # $14
            summary.precip_total_mm,       # $15
            summary.rain_total_mm,         # $16
            summary.snowfall_total_cm,     # $17
            summary.precip_hours,          # $18
            summary.precip_prob_max_pct,   # $19
            summary.wind_speed_max_kmh,    # $20
            summary.wind_gusts_max_kmh,    # $21
            summary.wind_dominant_cardinal, # $22
            summary.dominant_condition,    # $23
            summary.weather_code_dominant, # $24
            summary.uv_index_max,          # $25
            summary.sunrise_at,            # $26
            summary.sunset_at,             # $27
            summary.daylight_hours,        # $28
            summary.flag_extreme_heat_day, # $29
            summary.flag_heatwave_day,     # $30
            summary.flag_heavy_rain_day,   # $31
            summary.flag_storm_day,        # $32
            summary.flag_cold_wave_day,    # $33
            summary.worst_breach_severity  # $34
        )
