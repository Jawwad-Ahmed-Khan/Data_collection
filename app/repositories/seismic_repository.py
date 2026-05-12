"""
ClimaSync Collection Service — Seismic Repository
"""

import logging
from uuid import UUID, uuid4
from typing import Any
from decimal import Decimal

from app.database.connection import DatabasePool
from app.models.seismic_models import SeismicEventBase
from app.database.queries.seismic_queries import (
    UPSERT_SEISMIC_EVENT,
    GET_RECENT_SEISMIC_EVENTS,
    DELETE_OLD_SEISMIC_EVENTS,
    GET_NEAREST_LOCATION
)

logger = logging.getLogger(__name__)

def to_str(val: Any) -> str | None:
    """Helper to convert to string or None."""
    return str(val) if val is not None else None

class SeismicRepository:
    def __init__(self, db: DatabasePool):
        self.db = db

    async def find_nearest_location(self, lon: float, lat: float) -> tuple[dict[str, Any] | None, float | None]:
        """Find the nearest active Pakistan location using PostGIS <-> operator."""
        row = await self.db.fetch_one(GET_NEAREST_LOCATION, lon, lat)
        if not row:
            return None, None
        return dict(row), float(row["distance_km"])

    async def upsert_event(self, event: SeismicEventBase, cycle_id: UUID) -> tuple[UUID, bool]:
        """Insert or update a seismic event in the database."""
        # Ensure usgs_event_url is present
        usgs_url = getattr(event, 'usgs_event_url', None)
        if not usgs_url and event.usgs_event_id:
            usgs_url = f"https://earthquake.usgs.gov/earthquakes/eventpage/{event.usgs_event_id}"

        # Pass numeric values as Decimal objects
        params = [
            uuid4(),                      # $1: event_id
            event.usgs_event_id,          # $2
            usgs_url,                     # $3
            cycle_id,                     # $4
            event.magnitude,              # $5: numeric
            event.magnitude_type,         # $6
            event.latitude,               # $7: numeric
            event.longitude,              # $8: numeric
            event.depth_km,               # $9: numeric
            event.usgs_place,             # $10
            event.resolved_district,      # $11
            event.resolved_province,      # $12
            event.nearest_location_id,    # $13
            event.distance_to_nearest_km, # $14: numeric
            event.felt_reports,           # $15
            event.cdi,                    # $16: numeric
            event.mmi,                    # $17: numeric
            event.tsunami_flag,           # $18
            event.usgs_alert_level,       # $19
            event.significance,           # $20
            event.station_count,          # $21
            event.azimuthal_gap_deg,      # $22: numeric
            event.rms_seconds,            # $23: numeric
            event.data_quality,           # $24
            event.contributing_networks,  # $25
            event.has_breach,             # $26
            event.breach_severity,        # $27
            event.threshold_id,           # $28
            event.usgs_last_updated_at,   # $29
            event.earthquake_time,        # $30
            event.model_dump_json()       # $31: raw_api_response
        ]

        try:
            row = await self.db.fetch_one(UPSERT_SEISMIC_EVENT, *params)
            if row:
                return row['event_id'], row['was_inserted']
            return params[0], True
        except Exception as e:
            logger.error("Seismic UPSERT failed for %s: %s", event.usgs_event_id, str(e))
            raise

    async def get_recent_events(self) -> list[dict[str, Any]]:
        """Get seismic events from the last 24 hours."""
        return await self.db.fetch_many(GET_RECENT_SEISMIC_EVENTS)

    async def cleanup_old_events(self) -> int:
        """Delete old seismic events."""
        return await self.db.execute(DELETE_OLD_SEISMIC_EVENTS)
