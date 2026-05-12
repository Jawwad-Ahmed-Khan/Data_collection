"""
ClimaSync Collection Service — Cycle Repository
"""

import json
from typing import Any
from uuid import UUID

from app.models.cycle_models import CollectionCycle
from app.repositories.base_repository import BaseRepository
from app.database.queries.cycle_queries import (
    INSERT_CYCLE,
    UPDATE_CYCLE,
    GET_MOST_RECENT_CYCLE,
)


class CycleRepository(BaseRepository):
    """Manages the collection cycle tracking logs."""

    async def start_cycle(self, api_id: str, api_name: str = "unknown", cycle_type: str = "scheduled") -> UUID:
        """Create a new cycle in running status. Returns the cycle_id UUID."""
        row = await self.db.fetch_one(INSERT_CYCLE, api_id, api_name, cycle_type)
        if not row:
            raise RuntimeError("INSERT_CYCLE failed to return cycle_id")
        return row["cycle_id"]

    async def complete_cycle(
        self,
        cycle_id: UUID | str,
        status: str,
        locations_targeted: int = 0,
        locations_success: int = 0,
        locations_failed: int = 0,
        rows_upserted: int = 0,
        rows_inserted: int = 0,
        breaches_triggered: int = 0,
        rate_limit_hits: int = 0,
        failure_reason: str | None = None,
        error_summary: dict[str, Any] | None = None,
        avg_latency_ms: float | None = None,
    ) -> None:
        """Update cycle with final metrics and status."""
        error_json = json.dumps(error_summary) if error_summary else None
        await self.db.execute(
            UPDATE_CYCLE,
            cycle_id,
            status,
            locations_targeted,
            locations_success,
            locations_failed,
            rows_upserted,
            rows_inserted,
            breaches_triggered,
            rate_limit_hits,
            failure_reason,
            error_json,
            avg_latency_ms,
        )

    async def get_most_recent_cycle(self, api_id: int) -> CollectionCycle | None:
        """Fetch the most recent cycle for a given API."""
        row = await self.db.fetch_one(GET_MOST_RECENT_CYCLE, api_id)
        if not row:
            return None
        return CollectionCycle(**row)
