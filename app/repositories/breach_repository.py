"""
ClimaSync Collection Service — Breach Repository
"""

from datetime import datetime
from uuid import UUID

from app.models.breach_models import ThresholdBreachLogBase
from app.repositories.base_repository import BaseRepository
from app.database.queries.breach_queries import (
    INSERT_BREACH_LOG,
    MARK_BREACH_DISPATCHED,
    MARK_BREACH_FAILED,
    FIND_RECENT_BREACH,
    GET_UNDISPATCHED_BREACHES,
)


class BreachRepository(BaseRepository):
    """Manages the lifecycle of threshold breach alerts."""

    async def insert_breach(
        self,
        breach: ThresholdBreachLogBase,
        is_duplicate: bool = False,
        duplicate_of_breach_id: UUID | None = None,
    ) -> str:
        """Insert a newly detected breach alert into the queue. Returns the UUID."""
        row = await self.db.fetch_one(
            INSERT_BREACH_LOG,
            breach.source_api,
            breach.threshold_id,
            breach.weather_location_id,
            breach.seismic_event_id,
            breach.gauge_id,
            breach.disaster_kind,
            breach.metric_name,
            breach.location_name,
            breach.district,
            breach.province,
            breach.latitude,
            breach.longitude,
            breach.observed_value,
            breach.threshold_value,
            breach.breach_severity,
            breach.excess_amount,
            breach.excess_pct,
            breach.observation_time,
            breach.is_forecast_breach,
            breach.forecast_horizon_h,
            is_duplicate,
            duplicate_of_breach_id,
        )
        if not row:
            raise RuntimeError("INSERT_BREACH_LOG failed to return breach_id")
        return str(row["breach_id"])

    async def find_recent_breach(
        self,
        metric_name: str,
        since: datetime,
        location_id: UUID | None = None,
    ) -> UUID | None:
        """Find a recent non-duplicate breach for the same metric and location.
        
        Args:
            metric_name: Metric that breached.
            since: Only consider breaches after this time.
            location_id: Location ID (weather_location_id or gauge_id).
        
        Returns:
            UUID of recent breach if found, None otherwise.
        """
        row = await self.db.fetch_one(
            FIND_RECENT_BREACH,
            metric_name,
            since,
            location_id,
        )
        return UUID(row["breach_id"]) if row else None

    async def get_undispatched_breaches(
        self,
        max_attempts: int,
        batch_size: int,
    ) -> list[dict]:
        """Fetch pending breaches that need to be dispatched.
        
        Args:
            max_attempts: Maximum dispatch attempts before giving up.
            batch_size: Number of breaches to fetch.
        
        Returns:
            List of breach dictionaries ready for dispatch.
        """
        rows = await self.db.fetch_many(
            GET_UNDISPATCHED_BREACHES,
            max_attempts,
            batch_size,
        )
        return [dict(row) for row in rows]

    async def mark_dispatched(self, breach_id: str) -> None:
        """Mark a breach as successfully dispatched to the main system."""
        await self.db.execute(MARK_BREACH_DISPATCHED, breach_id)

    async def mark_dispatch_failed(self, breach_id: str, error_msg: str) -> None:
        """Mark a breach as failed so the dispatcher can retry it later."""
        await self.db.execute(MARK_BREACH_FAILED, breach_id, error_msg)
