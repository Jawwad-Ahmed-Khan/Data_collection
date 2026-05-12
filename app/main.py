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
    try:
        _db_pool = DatabasePool(settings)
        await _db_pool.connect()
        logger.info("✓ Step 3/7: Database connected (pool_size=%d-%d)", 
                    settings.collection_db_pool_min, settings.collection_db_pool_max)
    except Exception as e:
        logger.critical("CRITICAL: Failed to connect to database at startup: %s", str(e))
        import sys
        sys.exit(1)

    # Step 3.5: Seed database
    logger.info("Checking and seeding reference data...")
    try:
        # Clean up any cycles left 'running' from a previous crash
        fixed_weather = await _db_pool.execute("""
            UPDATE collection_cycles
            SET status = 'failed', completed_at = now(), failure_reason = 'Service restarted — cycle was interrupted'
            WHERE status = 'running' AND api_name = 'open_meteo' AND started_at < now() - INTERVAL '30 minutes'
        """)
        if fixed_weather != 'UPDATE 0':
            logger.warning("Fixed stale weather cycles: %s", fixed_weather)

        fixed_flood = await _db_pool.execute("""
            UPDATE collection_cycles
            SET status = 'failed', completed_at = now(), failure_reason = 'Service restarted — cycle was interrupted'
            WHERE status = 'running' AND api_name = 'google_flood_hub' AND started_at < now() - INTERVAL '15 minutes'
        """)
        if fixed_flood != 'UPDATE 0':
            logger.warning("Fixed stale flood cycles: %s", fixed_flood)

        # Seed APIs
        await _db_pool.execute("""
            INSERT INTO api_registry (
                api_name, display_name, base_url, documentation_url,
                max_requests_per_minute, min_delay_between_calls_ms,
                initial_backoff_s, max_backoff_s, backoff_multiplier
            )
            VALUES 
                ('usgs', 'USGS Earthquake API', 'https://earthquake.usgs.gov/fdsnws/event/1/query', 'https://earthquake.usgs.gov/fdsnws/event/1/', 60, 300, 5, 600, 2.0),
                ('open_meteo', 'Open-Meteo Weather API', 'https://api.open-meteo.com/v1/forecast', 'https://open-meteo.com/en/docs', 10, 500, 10, 600, 2.0),
                ('google_flood_hub', 'Google Flood Hub API', 'https://floodforecasting.googleapis.com/v1', 'https://developers.google.com/earth-engine/guides/flood_hub', 60, 500, 10, 600, 2.0)
            ON CONFLICT DO NOTHING
        """)
        logger.info("api_registry seeded/verified")
        
        # Seed Disaster Thresholds
        await _db_pool.execute("""
            INSERT INTO disaster_thresholds (
                disaster_kind, metric_name, breach_direction, unit, 
                watch_threshold, warning_threshold, emergency_threshold, extreme_threshold,
                province, applies_season, is_active
            ) VALUES 
                ('earthquake', 'magnitude', 'above', 'richter', 4.0, 5.0, 6.0, 7.0, NULL, NULL, TRUE),
                ('flood', 'gauge_pct_of_danger', 'above', 'percent', 60.0, 80.0, 100.0, 120.0, NULL, NULL, TRUE),
                ('heatwave', 'temp_max_c', 'above', 'celsius', 40.0, 42.0, 45.0, 48.0, NULL, 'summer', TRUE),
                ('heatwave', 'temp_max_c', 'above', 'celsius', 42.0, 45.0, 48.0, 50.0, 'sindh', 'summer', TRUE),
                ('heavy_rain', 'precip_1h_mm', 'above', 'mm', 20.0, 30.0, 40.0, 50.0, NULL, NULL, TRUE),
                ('heavy_rain', 'precip_24h_mm', 'above', 'mm', 50.0, 75.0, 100.0, 150.0, NULL, NULL, TRUE),
                ('cyclone', 'wind_gusts_kmh', 'above', 'kmh', 65.0, 90.0, 120.0, 160.0, NULL, NULL, TRUE),
                ('cyclone', 'cape_jkg', 'above', 'j/kg', 1000.0, 2000.0, 3000.0, 4000.0, NULL, NULL, TRUE),
                ('cold_wave', 'temp_min_c', 'below', 'celsius', 5.0, 2.0, -2.0, -5.0, NULL, 'winter', TRUE),
                ('cold_wave', 'temp_min_c', 'below', 'celsius', -2.0, -5.0, -10.0, -15.0, 'gilgit_baltistan', 'winter', TRUE)
            ON CONFLICT DO NOTHING
        """)

        # Seed Locations
        loc_count_row = await _db_pool.fetch_one("SELECT count(*) as cnt FROM pakistan_locations WHERE is_active = TRUE")
        if loc_count_row and loc_count_row["cnt"] < 15:
            locations = [
                ("lahore_31.5497_74.3436", "Lahore", "لاہور", "tier_1_provincial_capital", "Lahore", "Lahore", "punjab", 31.5497, 74.3436, "II", 11126285, "zone_1_low", "zone_3_high", "moderate", "critical", 180),
                ("karachi_24.8607_67.0011", "Karachi", "کراچی", "tier_1_provincial_capital", "Karachi", "Karachi", "sindh", 24.8607, 67.0011, "III", 16051521, "zone_2_moderate", "zone_5_critical", "low", "critical", 180),
                ("islamabad_33.6844_73.0479", "Islamabad", "اسلام آباد", "tier_1_provincial_capital", "Islamabad", "Islamabad", "islamabad_capital_territory", 33.6844, 73.0479, "III", 1014825, "zone_1_low", "zone_2_moderate", "moderate", "critical", 180),
                ("peshawar_34.0150_71.5249", "Peshawar", "پشاور", "tier_1_provincial_capital", "Peshawar", "Peshawar", "khyber_pakhtunkhwa", 34.0150, 71.5249, "IV", 1970042, "zone_2_moderate", "zone_2_moderate", "moderate", "critical", 180),
                ("quetta_30.1798_66.9750", "Quetta", "کوئٹہ", "tier_1_provincial_capital", "Quetta", "Quetta", "balochistan", 30.1798, 66.9750, "IV", 1001205, "zone_1_low", "zone_3_high", "low", "critical", 180),
                ("multan_30.1575_71.5249", "Multan", "ملتان", "tier_2_district_headquarters", "Multan", "Multan", "punjab", 30.1575, 71.5249, "II", 1871843, "zone_1_low", "zone_4_very_high", "moderate", "high", 240),
                ("faisalabad_31.4504_73.1350", "Faisalabad", "فیصل آباد", "tier_2_district_headquarters", "Faisalabad", "Faisalabad", "punjab", 31.4504, 73.1350, "II", 3203846, "zone_1_low", "zone_3_high", "moderate", "high", 240),
                ("hyderabad_25.3960_68.3578", "Hyderabad", "حیدرآباد", "tier_2_district_headquarters", "Hyderabad", "Hyderabad", "sindh", 25.3960, 68.3578, "II", 1734302, "zone_2_moderate", "zone_4_very_high", "low", "high", 240),
                ("sukkur_27.7135_68.8524", "Sukkur", "سکھر", "tier_2_district_headquarters", "Sukkur", "Sukkur", "sindh", 27.7135, 68.8524, "II", 499900, "zone_5_critical", "zone_4_very_high", "low", "high", 240),
                ("gilgit_35.9208_74.3083", "Gilgit", "گلگت", "tier_2_district_headquarters", "Gilgit", "Gilgit", "gilgit_baltistan", 35.9208, 74.3083, "IV", 216760, "zone_2_moderate", "zone_1_low", "moderate", "high", 240),
                ("muzaffarabad_34.3596_73.4715", "Muzaffarabad", "مظفرآباد", "tier_2_district_headquarters", "Muzaffarabad", "Muzaffarabad", "azad_kashmir", 34.3596, 73.4715, "IV", 149000, "zone_2_moderate", "zone_1_low", "moderate", "high", 240),
                ("abbottabad_34.1463_73.2117", "Abbottabad", "ایبٹ آباد", "tier_2_district_headquarters", "Abbottabad", "Abbottabad", "khyber_pakhtunkhwa", 34.1463, 73.2117, "IV", 208491, "zone_2_moderate", "zone_1_low", "moderate", "high", 240),
                ("larkana_27.5589_68.2120", "Larkana", "لاڑکانہ", "tier_3_disaster_zone", "Larkana", "Larkana", "sindh", 27.5589, 68.2120, "II", 490508, "zone_5_critical", "zone_4_very_high", "low", "medium", 360),
                ("dera_ghazi_khan_30.0489_70.6455", "Dera Ghazi Khan", "ڈیرہ غازی خان", "tier_3_disaster_zone", "Dera Ghazi Khan", "Dera Ghazi Khan", "punjab", 30.0489, 70.6455, "III", 399064, "zone_5_critical", "zone_4_very_high", "low", "medium", 360),
                ("chaman_30.9236_66.4512", "Chaman", "چمن", "tier_3_disaster_zone", "Chaman", "Chaman", "balochistan", 30.9236, 66.4512, "IV", 123190, "zone_1_low", "zone_2_moderate", "low", "medium", 360),
            ]
            for loc in locations:
                await _db_pool.execute("""
                    INSERT INTO pakistan_locations (
                        location_key, location_name, local_name, location_tier, 
                        district, division, province, latitude, longitude,
                        seismic_zone, population, flood_risk_zone, heat_risk_zone,
                        infrastructure_quality, poll_priority, poll_interval_minutes,
                        next_poll_due_at, coordinates, is_active
                    ) VALUES (
                        $1, $2, $3, $4::location_tier, 
                        $5, $6, $7::pk_province, $8::numeric, $9::numeric, 
                        $10, $11, $12::risk_zone, $13::risk_zone, 
                        $14::vulnerability_level, $15::poll_priority, $16,
                        now(), ST_SetSRID(ST_MakePoint($9::float8, $8::float8), 4326), TRUE
                    )
                    ON CONFLICT DO NOTHING
                """, *loc)
            logger.info("Seeded 15 prototype locations.")

        # Seed Gauges
        gauge_count_row = await _db_pool.fetch_one("SELECT count(*) as cnt FROM flood_gauge_registry WHERE is_active = TRUE")
        if gauge_count_row and gauge_count_row["cnt"] < 9:
            import json
            import os
            # Read first 9 gauges from active_gauges.json
            gauge_path = "active_gauges.json"
            if os.path.exists(gauge_path):
                with open(gauge_path, "r") as f:
                    all_gauges = json.load(f)
                
                # Take first 9
                for gauge in all_gauges[:9]:
                    await _db_pool.execute("""
                        INSERT INTO flood_gauge_registry (
                            google_gauge_id, gauge_name, river_name, coordinates, latitude, longitude,
                            province, district, poll_priority, is_active,
                            warning_level_m, danger_level_m, extreme_level_m, historical_max_m
                        ) VALUES (
                            $1, $2, $3, ST_GeogFromText($4), $5, $6, $7::pk_province, $8, $9::poll_priority, TRUE,
                            $10, $11, $12, $13
                        )
                        ON CONFLICT DO NOTHING
                    """,
                    gauge["google_gauge_id"], gauge.get("gauge_name", "Unnamed"), "Unnamed River",
                    f"POINT({gauge['lon']} {gauge['lat']})",
                    gauge["lat"], gauge["lon"], None, "Unknown", "high",
                    10.0, 12.0, 15.0, 20.0
                    )
                logger.info("Seeded 9 active flood gauges.")
                
                # Link nearest_location_id
                await _db_pool.execute("""
                    UPDATE flood_gauge_registry SET nearest_location_id = (
                        SELECT location_id FROM pakistan_locations
                        ORDER BY coordinates <-> flood_gauge_registry.coordinates
                        LIMIT 1
                    )
                    WHERE nearest_location_id IS NULL AND is_active = TRUE
                """)
                logger.info("Linked nearest locations to flood gauges.")
    except Exception as e:
        logger.error("Failed during seeding: %s", str(e))

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
        SELECT gauge_id, google_gauge_id, gauge_name, river_name, river_system,
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
        timeout=httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=30.0),
        limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        headers={"User-Agent": "ClimaSync-Data-Collection-Service/1.0"},
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
    if not settings.google_flood_hub_api_key:
        logger.critical("CRITICAL: GOOGLE_FLOOD_HUB_API_KEY is missing. Flood Hub collector will be disabled.")
        _floodhub_collector = None
    else:
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
    
    app.state.scheduler = _scheduler
    app.state.openmeteo_collector = _openmeteo_collector
    app.state.usgs_collector = _usgs_collector
    app.state.floodhub_collector = _floodhub_collector
    
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
            "DELETE FROM weather_daily_summaries WHERE summary_date < $1",
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
    try:
        _scheduler.start()
    except Exception as e:
        logger.critical("CRITICAL: Failed to start scheduler: %s", str(e))
        import sys
        sys.exit(1)
    
    logger.info("✓ Step 6/7: Scheduler started with 7 jobs:")

    # Step 7: Set database pool for API routes
    health_controller.set_database_pool(_db_pool)
    health_controller.set_scheduler(_scheduler)
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
