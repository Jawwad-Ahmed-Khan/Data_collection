import asyncio
import asyncpg
from app.core.config import get_settings

async def check_all_apis():
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_dsn, statement_cache_size=0)
    try:
        print("--- Global Data Check ---")
        
        # Seismic
        seismic_count = await conn.fetchval("SELECT count(*) FROM seismic_events")
        print(f"Seismic Events: {seismic_count}")
        
        # Flood Gauges
        active_gauges = await conn.fetchval("SELECT count(*) FROM flood_gauge_registry WHERE is_active = TRUE")
        flood_readings = await conn.fetchval("SELECT count(*) FROM flood_gauge_current")
        flood_forecasts = await conn.fetchval("SELECT count(*) FROM flood_gauge_forecasts")
        print(f"Active Flood Gauges: {active_gauges}")
        print(f"Flood Current Readings: {flood_readings}")
        print(f"Flood Forecast Records: {flood_forecasts}")
        
        # Weather (Just to be sure)
        weather_hourly = await conn.fetchval("SELECT count(*) FROM weather_hourly_window")
        weather_daily = await conn.fetchval("SELECT count(*) FROM weather_daily_summaries")
        print(f"Weather Hourly Windows: {weather_hourly}")
        print(f"Weather Daily Summaries: {weather_daily}")

        # Check if any seismic events are near our 3 locations
        print("\n--- Geographic Relevance ---")
        near_events = await conn.fetch("SELECT nearest_location_id, count(*) FROM seismic_events GROUP BY nearest_location_id")
        for r in near_events:
            loc_name = await conn.fetchval("SELECT location_name FROM pakistan_locations WHERE location_id = $1", r['nearest_location_id'])
            print(f"Seismic Events near {loc_name}: {r['count']}")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_all_apis())
