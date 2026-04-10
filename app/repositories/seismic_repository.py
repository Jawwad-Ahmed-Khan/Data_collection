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
            # Generate UUID in Python? No, standard query expects UUID generation on insertion or we pass it?
            # Wait, the SQL query expects:
            # $1: event_id, $2: usgs_event_id, ... 
            # We don't have event_id in SeismicEventBase. It only has usgs_event_id.
            # We must either generate event_id here or use a default uuid_generate_v4() in SQL.
            # However, looking at UPSERT_SEISMIC_EVENT we pass $1. Let's pass None and assume the database
            # trigger or default handles it if we adjust the parameter to pass None or just let it use
            # gen_random_uuid(). Wait, the query explicitly lists 24 parameters including event_id.
            # Let's generate it using python uuid module.
            __import__("uuid").uuid4(),
            event.usgs_event_id,
            event.magnitude,
            event.magnitude_type,
            event.magnitude_class,
            event.depth_km,
            event.depth_class,
            event.latitude,
            event.longitude,
            event.usgs_place,
            event.resolved_district,
            event.resolved_province,
            event.nearest_location_id,
            event.distance_to_nearest_km,
            event.felt_reports,
            event.cdi,
            event.mmi,
            event.tsunami_flag,
            event.usgs_alert_level,
            event.significance,
            event.data_quality,
            event.earthquake_time,
            event.has_breach,
            event.breach_severity,
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
