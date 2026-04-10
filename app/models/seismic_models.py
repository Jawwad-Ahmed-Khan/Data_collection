"""
ClimaSync Collection Service — Seismic Models
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class SeismicEventBase(BaseModel):
    usgs_event_id: str
    magnitude: float
    magnitude_type: str | None = None
    magnitude_class: Literal["micro", "minor", "light", "moderate", "strong", "major", "great"]
    depth_km: float
    depth_class: Literal["shallow", "intermediate", "deep"]
    latitude: float
    longitude: float
    usgs_place: str | None = None
    resolved_district: str | None = None
    resolved_province: str | None = None
    nearest_location_id: UUID | None = None
    distance_to_nearest_km: float | None = None
    felt_reports: int | None = None
    cdi: float | None = None
    mmi: float | None = None
    tsunami_flag: bool = False
    usgs_alert_level: Literal["green", "yellow", "orange", "red"] | None = None
    significance: int | None = None
    data_quality: Literal["automatic", "reviewed", "deleted"] = "automatic"
    earthquake_time: datetime
    has_breach: bool = False
    breach_severity: Literal["watch", "warning", "emergency", "extreme"] | None = None


class SeismicEvent(SeismicEventBase):
    event_id: str
    initial_magnitude: float | None = None
    magnitude_was_revised: bool = False
    first_seen_at: datetime
    last_refreshed_at: datetime
