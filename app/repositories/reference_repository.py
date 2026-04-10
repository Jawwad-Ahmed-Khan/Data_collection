"""
ClimaSync Collection Service — Reference Repository
"""

from datetime import datetime

from app.models.reference_models import ApiRegistry, DisasterThreshold, PakistanLocation
from app.repositories.base_repository import BaseRepository
from app.database.queries.reference_queries import (
    GET_API_BY_NAME,
    UPDATE_API_BACKOFF,
    GET_ALL_THRESHOLDS,
    GET_ACTIVE_LOCATIONS,
)


class ReferenceRepository(BaseRepository):
    """Handles fetching reference data that tells collectors what to do."""

    async def get_api_by_name(self, api_name: str) -> ApiRegistry | None:
        """Fetch API configuration and health limits by name."""
        row = await self.db.fetch_one(GET_API_BY_NAME, api_name)
        if not row:
            return None
        return ApiRegistry(**row)

    async def update_api_backoff(self, api_name: str, backoff_until: datetime) -> None:
        """Set the backoff timestamp for an API when rate limited."""
        await self.db.execute(UPDATE_API_BACKOFF, api_name, backoff_until)

    async def get_all_thresholds(self) -> list[DisasterThreshold]:
        """Fetch all active disaster thresholds."""
        rows = await self.db.fetch_many(GET_ALL_THRESHOLDS)
        return [DisasterThreshold(**row) for row in rows]

    async def get_active_locations(self) -> list[PakistanLocation]:
        """Fetch all active monitoring locations."""
        rows = await self.db.fetch_many(GET_ACTIVE_LOCATIONS)
        return [PakistanLocation(**row) for row in rows]
