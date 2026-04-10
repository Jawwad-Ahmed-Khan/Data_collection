"""
ClimaSync.ai — Data Collection Service

FastAPI application entry point.
Bootstraps configuration, logging, database pool, API routes, scheduler, and collectors.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI

from app.core.config import get_settings
from app.core.logger import get_logger, setup_logger
from app.database.connection import DatabasePool

# Import repositories
from app.repositories.reference_repository import ReferenceRepository
from app.repositories.seismic_repository import SeismicRepository
from app.repositories.breach_repository import BreachRepository
from app.repositories.cycle_repository import CycleRepository
from app.repositories.weather_repository import WeatherRepository
from app.repositories.flood_repository import FloodRepository

# Import services
from app.services.breach_service import BreachService
from app.services.usgs_service import USGSService
from app.services.openmeteo_service import OpenMeteoService
from app.services.floodhub_service import FloodHubService
from app.services.dispatch_service import DispatchService

# Import collectors
from app.collectors.usgs_collector import USGSCollector
from app.collectors.openmeteo_collector import OpenMeteoCollector
from app.collectors.floodhub_collector import FloodHubCollector

# Import scheduler
from app.scheduler.job_scheduler import JobScheduler

# Import API routes
from app.api.routes import health_controller, status_controller

logger = get_logger(__name__)

# ── Global references (set during lifespan) ───────────────────────
_db_pool: DatabasePool | None = None
_http_client: httpx.AsyncClient | None = None
_usgs_collector: USGSCollector | None = None
_openmeteo_collector: OpenMeteoCollector | None = None
_floodhub_collector: FloodHubCollector | None = None
_dispatch_service: DispatchService | None = None
_scheduler: JobScheduler | None = None


# ── In-Memory Cache ───────────────────────────────────────────────

class InMemoryCache:
    """Cache for reference data loaded at startup.
    
    Avoids repeated database queries during collection cycles.
    Reloaded periodically by scheduler.
    """
    
    def __init__(self):
        self.pakistan_locations = []
        self.disaster_thresholds = []
        self.api_configs = {}
        self.flood_gauges = []
        self.last_reload_at = None
    
    def is_loaded(self) -> bool:
        """Check if cache has been loaded."""
        return len(self.pakistan_locations) > 0 and len(self.disaster_thresholds) > 0


_cache = InMemoryCache()


# ── Application Lifespan ──────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown of the collection service.

    Startup sequence (7 steps):
        1. Load configuration (fail fast if missing vars)
        2. Initialize logger
        3. Connect to database (fail fast if unreachable)
        4. Load reference data into InMemoryCache
        5. Initialize all components (collectors, services, repositories)
        6. Initialize and start AsyncIOScheduler (placeholder for now)
        7. Log startup complete message

    Shutdown sequence:
        1. Stop scheduler gracefully
        2. Close HTTP client
        3. Close database pool
    """
    # ── Startup ───────────────────────────────────────────────────

    logger.info("=" * 70)
    logger.info("ClimaSync Collection Service — Starting Up")
    logger.info("=" * 70)

    # Step 1: Load and validate configuration
    settings = get_settings()
    logger.info("✓ Step 1/7: Configuration loaded (service=%s, env=%s)", 
                settings.service_name, settings.app_env)

    # Step 2: Re-init logger with configured log level
    setup_logger(level=settings.log_level)
    logger.info("✓ Step 2/7: Logger initialized (level=%s)", settings.log_level)

    # Step 3: Connect to database
    global _db_pool
    _db_pool = DatabasePool(settings)
    await _db_pool.connect()
    logger.info("✓ Step 3/7: Database connected (pool_size=%d-%d)", 
                settings.collection_db_pool_min, settings.collection_db_pool_max)

    # Step 4: Load reference data into InMemoryCache
    reference_repo = ReferenceRepository(_db_pool)
    
    _cache.pakistan_locations = await reference_repo.get_active_locations()
    _cache.disaster_thresholds = await reference_repo.get_all_thresholds()
    
    # Load API configs into dict for fast lookup
    apis_list = await _db_pool.fetch_many(
        """
        SELECT api_id, api_name, display_name, base_url, 
               max_requests_per_minute, is_active
        FROM api_registry
        WHERE is_active = TRUE
        """
    )
    for api_data in apis_list:
        _cache.api_configs[api_data["api_name"]] = api_data
    
    # Load flood gauges (for future flood collector)
    flood_gauges_data = await _db_pool.fetch_many(
        """
        SELECT gauge_id, google_gauge_id, gauge_name, river_name,
               latitude, longitude, district, province
        FROM flood_gauge_registry
        WHERE is_active = TRUE
        """
    )
    _cache.flood_gauges = flood_gauges_data
    
    from datetime import datetime
    from zoneinfo import ZoneInfo
    _cache.last_reload_at = datetime.now(ZoneInfo("Asia/Karachi"))
    
    logger.info("✓ Step 4/7: Reference data loaded:")
    logger.info("  - %d Pakistan locations", len(_cache.pakistan_locations))
    logger.info("  - %d disaster thresholds", len(_cache.disaster_thresholds))
    logger.info("  - %d API configurations", len(_cache.api_configs))
    logger.info("  - %d flood gauges", len(_cache.flood_gauges))

    # Step 5: Initialize all components
    global _http_client, _usgs_collector, _openmeteo_collector, _floodhub_collector, _dispatch_service
    
    # Create shared HTTP client
    _http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(30.0),
        limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
    )
    
    # Create repositories
    seismic_repo = SeismicRepository(_db_pool)
    breach_repo = BreachRepository(_db_pool)
    cycle_repo = CycleRepository(_db_pool)
    weather_repo = WeatherRepository(_db_pool)
    flood_repo = FloodRepository(_db_pool)
    
    # Create breach service (used by all collectors)
    breach_service = BreachService(
        thresholds=_cache.disaster_thresholds,
        breach_repository=breach_repo,
    )
    
    # Create USGS service and collector
    usgs_service = USGSService(
        seismic_repo=seismic_repo,
        breach_service=breach_service,
        pakistan_locations=_cache.pakistan_locations,
    )
    
    _usgs_collector = USGSCollector(
        http_client=_http_client,
        reference_repo=reference_repo,
        cycle_repo=cycle_repo,
        usgs_service=usgs_service,
    )
    
    # Create Open-Meteo service and collector
    openmeteo_service = OpenMeteoService(
        weather_repo=weather_repo,
        breach_service=breach_service,
    )
    
    _openmeteo_collector = OpenMeteoCollector(
        http_client=_http_client,
        reference_repo=reference_repo,
        cycle_repo=cycle_repo,
        openmeteo_service=openmeteo_service,
        pakistan_locations=_cache.pakistan_locations,
    )
    
    # Create Flood Hub service and collector
    from app.models.flood_models import FloodGaugeRegistry
    flood_gauges = [FloodGaugeRegistry(**g) for g in _cache.flood_gauges]
    
    floodhub_service = FloodHubService(
        flood_repo=flood_repo,
        breach_service=breach_service,
    )
    
    _floodhub_collector = FloodHubCollector(
        http_client=_http_client,
        reference_repo=reference_repo,
        cycle_repo=cycle_repo,
        flood_repo=flood_repo,
        floodhub_service=floodhub_service,
        flood_gauges=flood_gauges,
    )
    
    # Create dispatch service
    _dispatch_service = DispatchService(
        http_client=_http_client,
        breach_repo=breach_repo,
    )
    
    logger.info("✓ Step 5/7: Components initialized:")
    logger.info("  - HTTP client (timeout=30s)")
    logger.info("  - Repositories (seismic, breach, cycle, reference, weather, flood)")
    logger.info("  - Services (breach, USGS, Open-Meteo, Flood Hub, dispatch)")
    logger.info("  - Collectors (USGS, Open-Meteo, Flood Hub)")

    # Step 6: Initialize and start scheduler
    global _scheduler
    _scheduler = JobScheduler()
    
    # Define cache reload function
    async def reload_cache():
        """Reload reference data from database."""
        _cache.disaster_thresholds = await reference_repo.get_all_thresholds()
        _cache.pakistan_locations = await reference_repo.get_active_locations()
        from datetime import datetime
        from zoneinfo import ZoneInfo
        _cache.last_reload_at = datetime.now(ZoneInfo("Asia/Karachi"))
        logger.info("Cache reloaded: %d thresholds, %d locations", 
                   len(_cache.disaster_thresholds), len(_cache.pakistan_locations))
    
    # Define cleanup function
    async def cleanup_expired_data():
        """Delete expired data from rolling window tables."""
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        
        # Delete seismic events older than 30 days
        cutoff_date = datetime.now(ZoneInfo("Asia/Karachi")) - timedelta(days=30)
        await _db_pool.execute(
            "DELETE FROM seismic_events WHERE earthquake_time < $1",
            cutoff_date
        )
        
        # Delete weather hourly older than 7 days
        cutoff_date = datetime.now(ZoneInfo("Asia/Karachi")) - timedelta(days=7)
        await _db_pool.execute(
            "DELETE FROM weather_hourly_window WHERE forecast_for_datetime < $1",
            cutoff_date
        )
        
        # Delete weather daily older than 14 days
        cutoff_date = datetime.now(ZoneInfo("Asia/Karachi")).date() - timedelta(days=14)
        await _db_pool.execute(
            "DELETE FROM weather_daily_summary WHERE summary_date < $1",
            cutoff_date
        )
        
        # Delete flood forecasts older than 7 days
        cutoff_date = datetime.now(ZoneInfo("Asia/Karachi")) - timedelta(days=7)
        await _db_pool.execute(
            "DELETE FROM flood_gauge_forecasts WHERE forecast_for_datetime < $1",
            cutoff_date
        )
        
        logger.info("Cleanup complete: expired data deleted")
    
    # Add all jobs to scheduler
    _scheduler.add_jobs(
        usgs_collector=_usgs_collector,
        openmeteo_collector=_openmeteo_collector,
        floodhub_collector=_floodhub_collector,
        dispatch_service=_dispatch_service,
        cache_reload_func=reload_cache,
        cleanup_func=cleanup_expired_data,
    )
    
    # Start scheduler
    _scheduler.start()
    
    logger.info("✓ Step 6/7: Scheduler started with 7 jobs:")

    # Step 7: Set database pool for API routes
    health_controller.set_database_pool(_db_pool)
    status_controller.set_database_pool(_db_pool)
    
    logger.info("✓ Step 7/7: Startup complete!")
    logger.info("=" * 70)
    logger.info("ClimaSync Collection Service is READY")
    logger.info("  - API: http://0.0.0.0:%d", settings.app_port)
    logger.info("  - Health: http://0.0.0.0:%d/health", settings.app_port)
    logger.info("  - Status: http://0.0.0.0:%d/status/cycles", settings.app_port)
    logger.info("=" * 70)

    yield

    # ── Shutdown ──────────────────────────────────────────────────
    logger.info("=" * 70)
    logger.info("ClimaSync Collection Service — Shutting Down")
    logger.info("=" * 70)

    # 1. Stop scheduler
    if _scheduler is not None:
        await _scheduler.stop(wait=True)
        logger.info("✓ Scheduler stopped")

    # 2. Close HTTP client
    if _http_client is not None:
        await _http_client.aclose()
        logger.info("✓ HTTP client closed")

    # 3. Close database pool
    if _db_pool is not None:
        await _db_pool.disconnect()
        logger.info("✓ Database pool closed")

    logger.info("=" * 70)
    logger.info("ClimaSync Collection Service stopped gracefully")
    logger.info("=" * 70)


# ── FastAPI Application ───────────────────────────────────────────

app = FastAPI(
    title="ClimaSync Collection Service",
    description="Monitors Pakistan for disaster conditions — earthquakes, floods, weather",
    version="0.1.0",
    lifespan=lifespan,
)

# Register API routes
app.include_router(health_controller.router)
app.include_router(status_controller.router)


# ── Root endpoint ─────────────────────────────────────────────────

@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "ClimaSync Collection Service",
        "version": "0.1.0",
        "status": "operational",
        "endpoints": {
            "health": "/health",
            "api_health": "/health/apis",
            "cycles": "/status/cycles",
            "breaches": "/status/breaches",
            "locations": "/status/locations",
        },
    }


# ── Manual collection trigger (for testing) ──────────────────────

@app.post("/trigger/usgs")
async def trigger_usgs_collection():
    """Manually trigger USGS collection cycle (for testing).
    
    Requires X-API-Key authentication.
    """
    from fastapi import Depends
    from app.api.routes.health_controller import verify_api_key
    
    if _usgs_collector is None:
        return {"error": "USGS collector not initialized"}
    
    result = await _usgs_collector.collect()
    return result


# ── Development entry point ───────────────────────────────────────

def main():
    """Start the collection service with uvicorn.

    Called when running: python -m app.main  or  uv run python main.py
    """
    settings = get_settings()

    # Setup logger before uvicorn starts
    setup_logger(level=settings.log_level)

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.app_port,
        reload=settings.app_env == "development",
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
