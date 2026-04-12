"""
ClimaSync Collection Service — Weather Models
"""

from datetime import datetime, date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class WeatherHourlyWindowBase(BaseModel):
    location_id: UUID
    location_key: str
    location_name: str
    district: str
    province: str
    latitude: Decimal
    longitude: Decimal
    forecast_for_datetime: datetime
    forecast_date: date
    day_offset: int
    temp_c: Decimal
    temp_apparent_c: Decimal
    temp_dewpoint_c: Decimal | None = None
    precip_mm: Decimal
    precip_prob_pct: int | None = None
    rain_mm: Decimal | None = None
    snowfall_cm: Decimal | None = None
    snow_depth_m: Decimal | None = None
    precip_3h_mm: Decimal | None = None
    precip_6h_mm: Decimal | None = None
    precip_12h_mm: Decimal | None = None
    precip_24h_mm: Decimal | None = None
    precip_72h_mm: Decimal | None = None
    wind_speed_kmh: Decimal | None = None
    wind_gusts_kmh: Decimal | None = None
    wind_direction_deg: int | None = None
    wind_direction_cardinal: str | None = None
    humidity_pct: int | None = None
    pressure_hpa: Decimal | None = None
    visibility_m: int | None = None
    cloud_cover_pct: int | None = None
    uv_index: Decimal | None = None
    cape_jkg: Decimal | None = None
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
    breach_observed_value: Decimal | None = None
    breach_threshold_value: Decimal | None = None
    threshold_id: UUID | None = None
    cycle_id: UUID | None = None
    data_freshness_minutes: int | None = None


class WeatherHourlyWindow(WeatherHourlyWindowBase):
    last_updated_at: datetime


class WeatherDailySummaryBase(BaseModel):
    location_id: UUID
    location_key: str
    location_name: str
    district: str
    province: str
    latitude: Decimal
    longitude: Decimal
    summary_date: date
    day_offset: int
    temp_max_c: Decimal
    temp_min_c: Decimal
    feels_like_max_c: Decimal | None = None
    feels_like_min_c: Decimal | None = None
    precip_total_mm: Decimal
    rain_total_mm: Decimal | None = None
    snowfall_total_cm: Decimal | None = None
    precip_hours: int | None = None
    precip_prob_max_pct: int | None = None
    wind_speed_max_kmh: Decimal | None = None
    wind_gusts_max_kmh: Decimal | None = None
    wind_dominant_cardinal: str | None = None
    dominant_condition: str | None = None
    weather_code_dominant: int | None = None
    uv_index_max: Decimal | None = None
    sunrise_at: datetime | None = None
    sunset_at: datetime | None = None
    daylight_hours: Decimal | None = None
    flag_extreme_heat_day: bool = False
    flag_heatwave_day: bool = False
    flag_heavy_rain_day: bool = False
    flag_storm_day: bool = False
    flag_cold_wave_day: bool = False
    worst_breach_severity: Literal["watch", "warning", "emergency", "extreme"] | None = None
    cycle_id: UUID | None = None
    data_freshness_minutes: int | None = None


class CurrentWeatherLocationBase(BaseModel):
    location_id: UUID
    location_key: str
    location_name: str
    temp_c: Decimal
    temp_apparent_c: Decimal | None = None
    precip_mm: Decimal | None = None
    wind_speed_kmh: Decimal | None = None
    humidity_pct: int | None = None
    pressure_hpa: Decimal | None = None
    weather_condition: str | None = None
    weather_description: str | None = None
    is_daytime: bool = True
    observation_time: datetime
    data_age_minutes: int | None = None
    data_freshness: str | None = None


class Weather5DaySummaryBase(BaseModel):
    location_id: UUID
    location_key: str
    location_name: str
    district: str
    province: str
    summary_date: date
    day_offset: int
    day_label: str | None = None
    temp_max_c: Decimal
    temp_min_c: Decimal
    feels_like_max_c: Decimal | None = None
    precip_total_mm: Decimal
    precip_prob_max_pct: int | None = None
    wind_speed_max_kmh: Decimal | None = None
    wind_gusts_max_kmh: Decimal | None = None
    uv_index_max: Decimal | None = None
    dominant_condition: str | None = None
    sunrise_at: datetime | None = None
    sunset_at: datetime | None = None
    flag_extreme_heat_day: bool = False
    flag_heatwave_day: bool = False
    flag_heavy_rain_day: bool = False
    flag_storm_day: bool = False
    flag_cold_wave_day: bool = False
    worst_breach_severity: Literal["watch", "warning", "emergency", "extreme"] | None = None
