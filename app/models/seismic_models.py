"""
ClimaSync Collection Service — Seismic Models
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class SeismicEventBase(BaseModel):
    usgs_event_id: str
    magnitude: Decimal
    magnitude_type: str | None = None
    magnitude_class: Literal["micro", "minor", "light", "moderate", "strong", "major", "great"]
    depth_km: Decimal
    depth_class: Literal["shallow", "intermediate", "deep"]
    latitude: Decimal
    longitude: Decimal
    usgs_place: str | None = None
    resolved_district: str | None = None
    resolved_province: str | None = None
    nearest_location_id: UUID | None = None
    distance_to_nearest_km: Decimal | None = None
    felt_reports: int | None = None
    cdi: Decimal | None = None
    mmi: Decimal | None = None
    tsunami_flag: bool = False
    usgs_alert_level: Literal["green", "yellow", "orange", "red"] | None = None
    significance: int | None = None
    station_count: int | None = None
    azimuthal_gap_deg: Decimal | None = None
    rms_seconds: Decimal | None = None
    contributing_networks: list[str] | None = None
    data_quality: Literal["automatic", "reviewed", "deleted"] = "automatic"
    earthquake_time: datetime
    usgs_last_updated_at: datetime | None = None
    has_breach: bool = False
    breach_severity: Literal["watch", "warning", "emergency", "extreme"] | None = None
    threshold_id: UUID | None = None


class SeismicEvent(SeismicEventBase):
    event_id: UUID
    usgs_event_url: str | None = None
    initial_magnitude: Decimal | None = None
    magnitude_was_revised: bool = False
    first_seen_at: datetime
    last_refreshed_at: datetime
