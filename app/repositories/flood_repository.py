"""
ClimaSync Collection Service — Flood Repository
"""

from app.models.flood_models import FloodGaugeCurrentBase, FloodGaugeForecastBase, FloodGaugeRegistry, FloodGaugeCurrent
from app.repositories.base_repository import BaseRepository
from app.database.queries.flood_queries import (
    UPSERT_FLOOD_CURRENT,
    UPSERT_FLOOD_FORECAST,
    GET_ACTIVE_FLOOD_GAUGES,
    GET_PREVIOUS_READING,
)


class FloodRepository(BaseRepository):
    """Handles Flood observations and probabilistic forecasts."""

    async def get_active_flood_gauges(self) -> list[FloodGaugeRegistry]:
        """Fetch all active flood gauges from registry."""
        rows = await self.db.fetch_many(GET_ACTIVE_FLOOD_GAUGES)
        return [FloodGaugeRegistry(**row) for row in rows]

    async def get_previous_reading(self, gauge_id: str) -> FloodGaugeCurrent | None:
        """Fetch the previous reading for a gauge.
        
        Args:
            gauge_id: Gauge ID to fetch reading for.
        
        Returns:
            Previous reading or None if not found.
        """
        row = await self.db.fetch_one(GET_PREVIOUS_READING, gauge_id)
        if row:
            return FloodGaugeCurrent(**row)
        return None

    async def upsert_current(self, current: FloodGaugeCurrentBase) -> None:
        """Insert or update reading bounds for the flood gauge current layer."""
        await self.db.execute(
            UPSERT_FLOOD_CURRENT,
            current.gauge_id,
            current.google_gauge_id,
            current.gauge_name,
            current.river_name,
            current.river_system,
            current.district,
            current.province,
            None,  # cycle_id
            current.reading_time,
            current.current_level_m,
            current.warning_level_m,
            current.danger_level_m,
            current.extreme_level_m,
            current.pct_of_warning,
            current.pct_of_danger,
            current.pct_of_historical_max,
            current.previous_level_m,
            current.level_change_m,
            current.rise_rate_m_per_hour,
            current.river_trend,
            current.hours_to_warning,
            current.hours_to_danger,
            current.flood_status,
            current.has_breach,
            current.breach_severity,
            None,  # threshold_id
            current.raw_api_response,
            __import__('datetime').datetime.now(__import__('zoneinfo').ZoneInfo("UTC"))
        )

    async def upsert_forecast_batch(self, forecasts: list[FloodGaugeForecastBase]) -> None:
        """Insert or update a probabilistic flood forecast point in bulk."""
        if not forecasts:
            return
            
        args = [
            (
                f.gauge_id,
                f.google_gauge_id,
                f.gauge_name,
                f.river_name,
                f.district,
                f.province,
                f.forecast_for_datetime,
                f.forecast_issued_at,
                f.level_p10_m,
                f.level_p50_m,
                f.level_p90_m,
                f.prob_exceeds_warning_pct,
                f.prob_exceeds_danger_pct,
                f.prob_exceeds_extreme_pct,
                f.forecast_status,
                f.worst_case_status,
                f.has_forecast_breach,
                f.breach_severity,
                f.raw_api_response,
            ) for f in forecasts
        ]
        
        await self.db.executemany(UPSERT_FLOOD_FORECAST, args)


