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
    DELETE_OLD_SEISMIC_EVENTS
)

logger = logging.getLogger(__name__)

def to_str(val: Any) -> str | None:
    """Helper to convert to string or None."""
    return str(val) if val is not None else None

class SeismicRepository:
    def __init__(self, db: DatabasePool):
        self.db = db

    async def upsert_event(self, event: SeismicEventBase, cycle_id: UUID) -> UUID:
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
            event.magnitude_class,        # $7
            event.latitude,               # $8: numeric
            event.longitude,              # $9: numeric
            event.depth_km,               # $10: numeric
            event.depth_class,            # $11
            event.usgs_place,             # $12
            event.resolved_district,      # $13
            event.resolved_province,      # $14
            event.nearest_location_id,    # $15
            event.distance_to_nearest_km, # $16: numeric
            event.felt_reports,           # $17
            event.cdi,                    # $18: numeric
            event.mmi,                    # $19: numeric
            event.tsunami_flag,           # $20
            event.usgs_alert_level,       # $21
            event.significance,           # $22
            event.station_count,          # $23
            event.azimuthal_gap_deg,      # $24: numeric
            event.rms_seconds,            # $25: numeric
            event.data_quality,           # $26
            event.contributing_networks,  # $27
            event.has_breach,             # $28
            event.breach_severity,        # $29
            event.threshold_id,           # $30
            event.usgs_last_updated_at,   # $31
            event.earthquake_time,        # $32
            event.model_dump_json()       # $33: raw_api_response
        ]

        try:
            row = await self.db.fetch_one(UPSERT_SEISMIC_EVENT, *params)
            if row:
                return row['event_id']
            return params[0]
        except Exception as e:
            logger.error("Seismic UPSERT failed for %s: %s", event.usgs_event_id, str(e))
            raise

    async def get_recent_events(self) -> list[dict[str, Any]]:
        """Get seismic events from the last 24 hours."""
        return await self.db.fetch_all(GET_RECENT_SEISMIC_EVENTS)

    async def cleanup_old_events(self) -> int:
        """Delete old seismic events."""
        return await self.db.execute(DELETE_OLD_SEISMIC_EVENTS)
