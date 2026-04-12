"""
ClimaSync Collection Service — Seismic Repository
"""

from app.models.seismic_models import SeismicEventBase, SeismicEvent
from app.repositories.base_repository import BaseRepository
from app.database.queries.seismic_queries import (
    UPSERT_SEISMIC_EVENT,
    GET_RECENT_SEISMIC_EVENTS,
    DELETE_OLD_SEISMIC_EVENTS,
)


class SeismicRepository(BaseRepository):
    """Handles UPSERTing earthquake data while tracking magnitude revisions."""

    async def upsert_event(self, event: SeismicEventBase) -> str:
        """Insert or update a seismic event. Returns the UUID of the inserted/updated row."""
        row = await self.db.fetch_one(
            UPSERT_SEISMIC_EVENT,
            __import__("uuid").uuid4(),   # $1: event_id
            event.usgs_event_id,          # $2
            event.usgs_event_url,         # $3
            event.magnitude,              # $4
            event.magnitude_type,         # $5
            event.magnitude_class,        # $6
            event.depth_km,               # $7
            event.depth_class,            # $8
            event.latitude,               # $9
            event.longitude,              # $10
            event.usgs_place,             # $11
            event.resolved_district,      # $12
            event.resolved_province,      # $13
            event.nearest_location_id,    # $14
            event.distance_to_nearest_km, # $15
            event.felt_reports,           # $16
            event.cdi,                    # $17
            event.mmi,                    # $18
            event.tsunami_flag,           # $19
            event.usgs_alert_level,       # $20
            event.significance,           # $21
            event.station_count,          # $22
            event.azimuthal_gap_deg,      # $23
            event.rms_seconds,            # $24
            event.data_quality,           # $25
            event.contributing_networks,  # $26
            event.earthquake_time,        # $27
            event.usgs_last_updated_at,   # $28
            event.has_breach,             # $29
            event.breach_severity,        # $30
            event.threshold_id,           # $31
        )
        if not row:
            raise RuntimeError("UPSERT_SEISMIC_EVENT failed to return event_id")
        return str(row["event_id"])

    async def get_recent_events(self) -> list[SeismicEvent]:
        """Fetch all M4.0+ events in the last 24 hours."""
        rows = await self.db.fetch_many(GET_RECENT_SEISMIC_EVENTS)
        return [SeismicEvent(**row) for row in rows]

    async def delete_old_events(self) -> None:
        """Explicitly run the cleanup query (though trigger/cron usually handles this)."""
        await self.db.execute(DELETE_OLD_SEISMIC_EVENTS)
