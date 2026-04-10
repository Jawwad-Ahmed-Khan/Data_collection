"""
ClimaSync Collection Service — Health Check Endpoints

Provides health status for monitoring and alerting.
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
from app.repositories.reference_repository import ReferenceRepository

router = APIRouter(prefix="/health", tags=["health"])
settings = get_settings()

# Pakistan Standard Time
_PKT = ZoneInfo("Asia/Karachi")

# Service start time for uptime calculation
_SERVICE_START_TIME = datetime.now(_PKT)

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


class HealthResponse(BaseModel):
    """Basic health check response."""
    status: str
    database_connected: bool
    uptime_seconds: float
    timestamp_pkt: datetime


class ApiHealthDetail(BaseModel):
    """Health details for a single API."""
    api_name: str
    display_name: str
    current_health: str
    last_success_at: datetime | None
    last_failure_at: datetime | None
    consecutive_failures: int
    is_in_backoff: bool
    backoff_remaining_seconds: float | None


class ApiHealthResponse(BaseModel):
    """Response with health status of all APIs."""
    apis: list[ApiHealthDetail]
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
    "",
    response_model=HealthResponse,
    summary="Basic health check",
    description="Returns service health status, database connectivity, and uptime.",
)
async def get_health(
    _: Annotated[None, Depends(verify_api_key)],
    db: Annotated[DatabasePool, Depends(get_database_pool)],
) -> HealthResponse:
    """Get basic service health status.
    
    Args:
        _: API key verification dependency.
        db: Database pool dependency.
    
    Returns:
        Health status response.
    """
    # Check database connectivity
    database_connected = db.is_connected
    
    # Calculate uptime
    now = datetime.now(_PKT)
    uptime_seconds = (now - _SERVICE_START_TIME).total_seconds()
    
    # Determine overall status
    service_status = "healthy" if database_connected else "degraded"
    
    return HealthResponse(
        status=service_status,
        database_connected=database_connected,
        uptime_seconds=uptime_seconds,
        timestamp_pkt=now,
    )


@router.get(
    "/apis",
    response_model=ApiHealthResponse,
    summary="API health status",
    description="Returns health status of all external APIs (USGS, Open-Meteo, Flood Hub).",
)
async def get_api_health(
    _: Annotated[None, Depends(verify_api_key)],
    db: Annotated[DatabasePool, Depends(get_database_pool)],
) -> ApiHealthResponse:
    """Get health status of all external APIs.
    
    Args:
        _: API key verification dependency.
        db: Database pool dependency.
    
    Returns:
        API health status response.
    """
    # Create reference repository
    reference_repo = ReferenceRepository(db)
    
    # Fetch all API configurations
    apis_data = await db.fetch_many(
        """
        SELECT
            api_name,
            display_name,
            current_health,
            last_success_at,
            last_failure_at,
            consecutive_failures,
            backoff_until
        FROM api_registry
        WHERE is_active = TRUE
        ORDER BY api_name
        """
    )
    
    now = datetime.now(_PKT)
    api_details = []
    
    for api_data in apis_data:
        # Check if in backoff period
        backoff_until = api_data.get("backoff_until")
        is_in_backoff = False
        backoff_remaining_seconds = None
        
        if backoff_until and backoff_until > now:
            is_in_backoff = True
            backoff_remaining_seconds = (backoff_until - now).total_seconds()
        
        api_details.append(
            ApiHealthDetail(
                api_name=api_data["api_name"],
                display_name=api_data["display_name"],
                current_health=api_data["current_health"],
                last_success_at=api_data.get("last_success_at"),
                last_failure_at=api_data.get("last_failure_at"),
                consecutive_failures=api_data["consecutive_failures"],
                is_in_backoff=is_in_backoff,
                backoff_remaining_seconds=backoff_remaining_seconds,
            )
        )
    
    return ApiHealthResponse(
        apis=api_details,
        timestamp_pkt=now,
    )
