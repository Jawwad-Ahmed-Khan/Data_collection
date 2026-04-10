"""
ClimaSync Collection Service — Weather Models
"""

from datetime import datetime, date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class WeatherHourlyWindowBase(BaseModel):
    location_id: UUID
    location_key: str
    location_name: str
    district: str
    province: str
    latitude: float
    longitude: float
    forecast_for_datetime: datetime
    forecast_date: date
    day_offset: int
    temp_c: float
    temp_apparent_c: float
    temp_dewpoint_c: float | None = None
    precip_mm: float
    precip_prob_pct: int | None = None
    precip_24h_mm: float | None = None
    precip_72h_mm: float | None = None
    wind_speed_kmh: float | None = None
    wind_gusts_kmh: float | None = None
    wind_direction_deg: int | None = None
    wind_direction_cardinal: str | None = None
    humidity_pct: int | None = None
    pressure_hpa: float | None = None
    visibility_m: float | None = None
    uv_index: float | None = None
    cape_jkg: float | None = None
    weather_code: int | None = None
    weather_condition: str | None = None
    weather_description: str | None = None
    is_daytime: bool = True
    flag_extreme_heat: bool = False
    flag_heatwave: bool = False
    flag_heavy_rain: bool = False
    flag_very_heavy_rain: bool = False
    flag_storm: bool = False
    flag_severe_storm: bool = False
    flag_cold_wave: bool = False
    flag_dust_storm: bool = False
    flag_dense_fog: bool = False
    has_breach: bool = False
    breach_severity: Literal["watch", "warning", "emergency", "extreme"] | None = None
    breach_metric: str | None = None
    breach_observed_value: float | None = None


class WeatherHourlyWindow(WeatherHourlyWindowBase):
    last_updated_at: datetime


class WeatherDailySummaryBase(BaseModel):
    location_id: UUID
    location_key: str
    location_name: str
    district: str
    province: str
    latitude: float
    longitude: float
    summary_date: date
    day_offset: int
    temp_max_c: float
    temp_min_c: float
    feels_like_max_c: float | None = None
    feels_like_min_c: float | None = None
    precip_total_mm: float
    precip_prob_max_pct: int | None = None
    wind_speed_max_kmh: float | None = None
    wind_gusts_max_kmh: float | None = None
    uv_index_max: float | None = None
    sunrise_at: datetime | None = None
    sunset_at: datetime | None = None
    dominant_condition: str | None = None
    flag_extreme_heat_day: bool = False
    flag_heatwave_day: bool = False
    flag_heavy_rain_day: bool = False
    flag_storm_day: bool = False
    flag_cold_wave_day: bool = False
    worst_breach_severity: Literal["watch", "warning", "emergency", "extreme"] | None = None


class WeatherDailySummary(WeatherDailySummaryBase):
    last_updated_at: datetime
