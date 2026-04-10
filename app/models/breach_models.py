"""
ClimaSync Collection Service — Breach Models
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class ThresholdBreachLogBase(BaseModel):
    source_api: Literal["usgs", "open_meteo", "google_flood_hub", "pmd"]
    threshold_id: UUID | None = None
    weather_location_id: UUID | None = None
    seismic_event_id: UUID | None = None
    gauge_id: UUID | None = None
    disaster_kind: Literal[
        "earthquake",
        "flood",
        "flash_flood",
        "heatwave",
        "cyclone",
        "heavy_rain",
        "drought",
        "landslide",
        "dust_storm",
        "cold_wave",
    ]
    metric_name: str
    location_name: str | None = None
    district: str | None = None
    province: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    observed_value: float
    threshold_value: float
    breach_severity: Literal["watch", "warning", "emergency", "extreme"]
    excess_amount: float | None = None
    excess_pct: float | None = None
    observation_time: datetime
    is_forecast_breach: bool = False
    forecast_horizon_h: int | None = None


class ThresholdBreachLog(ThresholdBreachLogBase):
    breach_id: UUID
    is_duplicate: bool = False
    duplicate_of_breach_id: UUID | None = None
    dispatch_status: Literal["pending", "dispatched", "dispatch_failed", "ignored"] = "pending"
    dispatch_attempt_count: int = 0
    last_dispatch_error: str | None = None
    detected_at: datetime
    dispatched_at: datetime | None = None
