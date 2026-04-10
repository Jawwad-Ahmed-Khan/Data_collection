"""
ClimaSync Collection Service — Status Endpoints

Provides operational status and metrics for monitoring.
All endpoints require X-API-Key authentication.
"""

from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.security import validate_api_key
from app.database.connection import DatabasePool

router = APIRouter(prefix="/status", tags=["status"])
settings = get_settings()

# Pakistan Standard Time
_PKT = ZoneInfo("Asia/Karachi")

# Global database pool instance (will be set by main.py)
_db_pool: DatabasePool | None = None


def set_database_pool(db: DatabasePool) -> None:
    """Set the global database pool instance.
    
    Called by main.py during startup.
    """
    global _db_pool
    _db_pool = db


def get_database_pool() -> DatabasePool:
    """Get the database pool dependency.
    
    Returns:
        Database pool instance.
    
    Raises:
        RuntimeError: If database pool not initialized.
    """
    if _db_pool is None:
        raise RuntimeError("Database pool not initialized")
    return _db_pool


# ── Response Models ───────────────────────────────────────────────


class CycleDetail(BaseModel):
    """Details of a single collection cycle."""
    cycle_id: str
    api_name: str
    cycle_type: str
    status: str
    locations_targeted: int
    locations_success: int
    locations_failed: int
    rows_upserted: int
    breaches_triggered: int
    rate_limit_hits: int
    started_at: datetime
    completed_at: datetime | None
    duration_ms: int | None


class CyclesResponse(BaseModel):
    """Response with recent collection cycles."""
    cycles: list[CycleDetail]
    timestamp_pkt: datetime


class BreachSummary(BaseModel):
    """Summary of breach counts by status."""
    pending_count: int
    dispatched_count: int
    failed_count: int
    last_breach_at: datetime | None


class BreachesResponse(BaseModel):
    """Response with breach statistics."""
    summary: BreachSummary
    timestamp_pkt: datetime


class LocationStatus(BaseModel):
    """Status of a single monitoring location."""
    location_id: str
    location_name: str
    district: str
    province: str
    last_polled_at: datetime | None
    next_poll_due_at: datetime | None
    consecutive_failures: int
    poll_priority: str


class LocationsResponse(BaseModel):
    """Response with location polling status."""
    locations: list[LocationStatus]
    total_locations: int
    timestamp_pkt: datetime


# ── Dependencies ──────────────────────────────────────────────────


async def verify_api_key(
    x_api_key: Annotated[str | None, Header()] = None,
) -> None:
    """Verify X-API-Key header matches configured key.
    
    Args:
        x_api_key: API key from X-API-Key header.
    
    Raises:
        HTTPException: 403 if key is missing or invalid.
    """
    if not validate_api_key(x_api_key, settings.main_system_api_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing X-API-Key header",
        )


# ── Endpoints ─────────────────────────────────────────────────────


@router.get(
    "/cycles",
    response_model=CyclesResponse,
    summary="Recent collection cycles",
    description="Returns the last 10 collection cycles per API.",
)
async def get_cycles(
    _: Annotated[None, Depends(verify_api_key)],
    db: Annotated[DatabasePool, Depends(get_database_pool)],
) -> CyclesResponse:
    """Get recent collection cycles.
    
    Args:
        _: API key verification dependency.
        db: Database pool dependency.
    
    Returns:
        Recent cycles response.
    """
    # Fetch last 10 cycles per API
    cycles_data = await db.fetch_many(
        """
        WITH ranked_cycles AS (
            SELECT
                cycle_id,
                api_name,
                cycle_type,
                status,
                locations_targeted,
                locations_success,
                locations_failed,
                rows_upserted,
                breaches_triggered,
                rate_limit_hits,
                started_at,
                completed_at,
                duration_ms,
                ROW_NUMBER() OVER (PARTITION BY api_name ORDER BY started_at DESC) as rn
            FROM collection_cycles
        )
        SELECT
            cycle_id,
            api_name,
            cycle_type,
            status,
            locations_targeted,
            locations_success,
            locations_failed,
            rows_upserted,
            breaches_triggered,
            rate_limit_hits,
            started_at,
            completed_at,
            duration_ms
        FROM ranked_cycles
        WHERE rn <= 10
        ORDER BY api_name, started_at DESC
        """
    )
    
    cycles = [
        CycleDetail(
            cycle_id=str(cycle["cycle_id"]),
            api_name=cycle["api_name"],
            cycle_type=cycle["cycle_type"],
            status=cycle["status"],
            locations_targeted=cycle["locations_targeted"],
            locations_success=cycle["locations_success"],
            locations_failed=cycle["locations_failed"],
            rows_upserted=cycle["rows_upserted"],
            breaches_triggered=cycle["breaches_triggered"],
            rate_limit_hits=cycle["rate_limit_hits"],
            started_at=cycle["started_at"],
            completed_at=cycle.get("completed_at"),
            duration_ms=cycle.get("duration_ms"),
        )
        for cycle in cycles_data
    ]
    
    return CyclesResponse(
        cycles=cycles,
        timestamp_pkt=datetime.now(_PKT),
    )


@router.get(
    "/breaches",
    response_model=BreachesResponse,
    summary="Breach statistics",
    description="Returns breach counts by dispatch status and last breach time.",
)
async def get_breaches(
    _: Annotated[None, Depends(verify_api_key)],
    db: Annotated[DatabasePool, Depends(get_database_pool)],
) -> BreachesResponse:
    """Get breach statistics.
    
    Args:
        _: API key verification dependency.
        db: Database pool dependency.
    
    Returns:
        Breach statistics response.
    """
    # Get breach counts by status
    breach_stats = await db.fetch_one(
        """
        SELECT
            COUNT(*) FILTER (WHERE dispatch_status = 'pending') as pending_count,
            COUNT(*) FILTER (WHERE dispatch_status = 'dispatched') as dispatched_count,
            COUNT(*) FILTER (WHERE dispatch_status = 'dispatch_failed') as failed_count,
            MAX(detected_at) as last_breach_at
        FROM threshold_breach_log
        WHERE detected_at >= now() - interval '24 hours'
        """
    )
    
    summary = BreachSummary(
        pending_count=breach_stats["pending_count"] if breach_stats else 0,
        dispatched_count=breach_stats["dispatched_count"] if breach_stats else 0,
        failed_count=breach_stats["failed_count"] if breach_stats else 0,
        last_breach_at=breach_stats.get("last_breach_at") if breach_stats else None,
    )
    
    return BreachesResponse(
        summary=summary,
        timestamp_pkt=datetime.now(_PKT),
    )


@router.get(
    "/locations",
    response_model=LocationsResponse,
    summary="Location polling status",
    description="Returns polling status for all monitoring locations.",
)
async def get_locations(
    _: Annotated[None, Depends(verify_api_key)],
    db: Annotated[DatabasePool, Depends(get_database_pool)],
) -> LocationsResponse:
    """Get location polling status.
    
    Args:
        _: API key verification dependency.
        db: Database pool dependency.
    
    Returns:
        Location status response.
    """
    # Fetch location polling status
    locations_data = await db.fetch_many(
        """
        SELECT
            location_id,
            location_name,
            district,
            province,
            last_polled_at,
            next_poll_due_at,
            consecutive_failures,
            poll_priority
        FROM pakistan_locations
        WHERE is_active = TRUE
        ORDER BY poll_priority, location_name
        """
    )
    
    locations = [
        LocationStatus(
            location_id=str(loc["location_id"]),
            location_name=loc["location_name"],
            district=loc["district"],
            province=loc["province"],
            last_polled_at=loc.get("last_polled_at"),
            next_poll_due_at=loc.get("next_poll_due_at"),
            consecutive_failures=loc["consecutive_failures"],
            poll_priority=loc["poll_priority"],
        )
        for loc in locations_data
    ]
    
    return LocationsResponse(
        locations=locations,
        total_locations=len(locations),
        timestamp_pkt=datetime.now(_PKT),
    )
