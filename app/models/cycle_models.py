"""
ClimaSync Collection Service — Cycle Models
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class CollectionCycleBase(BaseModel):
    api_id: UUID
    status: Literal["running", "completed", "partial", "failed"]


class CollectionCycle(CollectionCycleBase):
    cycle_id: str
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int | None = None
    locations_targeted: int = 0
    locations_success: int = 0
    locations_failed: int = 0
    rows_upserted: int = 0
    rows_inserted: int = 0
    breaches_triggered: int = 0
    rate_limit_hits: int = 0
    created_at: datetime
    updated_at: datetime
