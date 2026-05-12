"""
ClimaSync Collection Service — Flood Models
"""

from datetime import datetime, date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class FloodGaugeRegistryBase(BaseModel):
    google_gauge_id: str
    gauge_name: str
    river_name: str
    river_system: str | None = None
    district: str | None = None
    province: str | None = None
    latitude: float
    longitude: float
    historical_max_m: float | None = None
    bankfull_level_m: float | None = None
    basin_name: str | None = None
    upstream_area_sqkm: float | None = None
    nearest_location_id: UUID | None = None
    warning_level_m: float | None = None
    danger_level_m: float | None = None
    extreme_level_m: float | None = None
    poll_priority: Literal["critical", "high", "normal"] = "normal"
    is_active: bool = True


class FloodGaugeRegistry(FloodGaugeRegistryBase):
    gauge_id: UUID


class FloodGaugeCurrentBase(BaseModel):
    gauge_id: UUID | str
    google_gauge_id: str
    gauge_name: str
    river_name: str
    river_system: str | None = None
    district: str | None = None
    province: str | None = None
    reading_time: datetime
    current_level_m: float
    warning_level_m: float | None = None
    danger_level_m: float | None = None
    extreme_level_m: float | None = None
    pct_of_warning: float | None = None
    pct_of_danger: float | None = None
    pct_of_historical_max: float | None = None
    previous_level_m: float | None = None
    level_change_m: float | None = None
    rise_rate_m_per_hour: float | None = None
    river_trend: Literal["rapidly_rising", "rising", "stable", "falling", "rapidly_falling"] = "stable"
    hours_to_warning: float | None = None
    hours_to_danger: float | None = None
    flood_status: Literal["no_flooding", "watch", "warning", "emergency"] = "no_flooding"
    has_breach: bool = False
    breach_severity: Literal["watch", "warning", "emergency", "extreme"] | None = None
    raw_api_response: dict | None = None


class FloodGaugeCurrent(FloodGaugeCurrentBase):
    collected_at: datetime


class FloodGaugeForecastBase(BaseModel):
    gauge_id: UUID | str
    google_gauge_id: str
    gauge_name: str | None = None
    river_name: str
    district: str | None = None
    province: str | None = None
    forecast_for_datetime: datetime
    forecast_issued_at: datetime
    forecast_date: date
    day_offset: int
    forecast_horizon_h: int
    level_p10_m: float | None = None
    level_p50_m: float
    level_p90_m: float | None = None
    prob_exceeds_warning_pct: float | None = None
    prob_exceeds_danger_pct: float | None = None
    prob_exceeds_extreme_pct: float | None = None
    forecast_status: Literal["no_flooding", "watch", "warning", "emergency"] = "no_flooding"
    worst_case_status: Literal["no_flooding", "watch", "warning", "emergency"] = "no_flooding"
    has_forecast_breach: bool = False
    breach_severity: Literal["watch", "warning", "emergency", "extreme"] | None = None
    raw_api_response: dict | None = None


class FloodGaugeForecast(FloodGaugeForecastBase):
    last_updated_at: datetime
