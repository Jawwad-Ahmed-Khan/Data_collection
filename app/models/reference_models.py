"""
ClimaSync Collection Service — Reference Models
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ApiRegistryBase(BaseModel):
    api_name: str
    display_name: str
    base_url: str
    documentation_url: str | None = None
    max_requests_per_minute: int = 60
    max_requests_per_day: int = 10000
    is_active: bool = True
    current_health: Literal["healthy", "degraded", "down", "rate_limited", "unknown"] = "unknown"
    consecutive_failures: int = 0
    backoff_until: datetime | None = None
    notes: str | None = None


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
    applies_season: str | None = None
    unit: str
    breach_direction: Literal["above", "below"]
    watch_threshold: Decimal | None = None
    warning_threshold: Decimal | None = None
    emergency_threshold: Decimal | None = None
    extreme_threshold: Decimal | None = None
    description: str | None = None
    is_active: bool = True


class PakistanLocation(BaseModel):
    location_id: UUID
    location_key: str
    location_name: str
    local_name: str | None = None
    location_tier: str
    district: str
    division: str | None = None
    province: str
    latitude: Decimal
    longitude: Decimal
    elevation_m: int | None = None
    population: int | None = None
    population_density: Decimal | None = None
    flood_risk_zone: str | None = None
    seismic_zone: str | None = None
    heat_risk_zone: str | None = None
    drought_risk_zone: str | None = None
    infrastructure_quality: str | None = None
    drainage_quality: str | None = None
    building_stock: str | None = None
    poll_priority: Literal["low", "medium", "high", "critical"] = "medium"
    poll_interval_minutes: int = 180
    last_polled_at: datetime | None = None
    last_poll_outcome: str | None = None
    next_poll_due_at: datetime | None = None
    consecutive_failures: int = 0
    is_active: bool = True
    data_source: str | None = None
