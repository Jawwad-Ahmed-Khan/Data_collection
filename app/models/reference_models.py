"""
ClimaSync Collection Service — Reference Models
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ApiRegistryBase(BaseModel):
    api_name: str
    display_name: str | None = None
    base_url: str
    max_requests_per_minute: int
    is_active: bool = True
    current_health: Literal["healthy", "degraded", "down", "rate_limited", "unknown"] | None = None
    consecutive_failures: int = 0
    backoff_until: datetime | None = None


class ApiRegistry(ApiRegistryBase):
    api_id: UUID
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    avg_latency_ms: float | None = None


class DisasterThreshold(BaseModel):
    threshold_id: UUID
    disaster_kind: str
    metric_name: str
    province: str | None = None
    district: str | None = None
    unit: str
    breach_direction: Literal["above", "below"]
    watch_threshold: float | None = None
    warning_threshold: float | None = None
    emergency_threshold: float | None = None
    extreme_threshold: float | None = None
    applies_season: str | None = None
    description: str | None = None
    is_active: bool = True


class PakistanLocation(BaseModel):
    location_id: UUID
    location_key: str
    location_name: str
    district: str
    province: str
    latitude: float
    longitude: float
    elevation_m: int | None = None
    population: int | None = None
    flood_risk_zone: str | None = None
    seismic_zone: str | None = None
    heat_risk_zone: str | None = None
    infrastructure_quality: int | None = None
    drainage_quality: int | None = None
    is_active: bool = True
