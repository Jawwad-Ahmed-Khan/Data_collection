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
        )

    async def upsert_forecast(self, forecast: FloodGaugeForecastBase) -> None:
        """Insert or update a probabilistic flood forecast point."""
        await self.db.execute(
            UPSERT_FLOOD_FORECAST,
            forecast.gauge_id,
            forecast.google_gauge_id,
            forecast.gauge_name,
            forecast.river_name,
            forecast.district,
            forecast.province,
            forecast.forecast_for_datetime,
            forecast.forecast_issued_at,
            forecast.forecast_date,
            forecast.day_offset,
            forecast.forecast_horizon_h,
            forecast.level_p10_m,
            forecast.level_p50_m,
            forecast.level_p90_m,
            forecast.prob_exceeds_warning_pct,
            forecast.prob_exceeds_danger_pct,
            forecast.forecast_status,
            forecast.worst_case_status,
            forecast.has_forecast_breach,
            forecast.breach_severity,
        )
