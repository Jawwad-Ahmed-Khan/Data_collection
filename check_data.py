import asyncio
import asyncpg
from app.core.config import get_settings

async def check_db():
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_dsn, statement_cache_size=0)
    try:
        print("--- Locations ---")
        locations = await conn.fetch("SELECT location_id, location_name, is_active FROM pakistan_locations")
        for loc in locations:
            print(f"ID: {loc['location_id']} | Name: {loc['location_name']} | Active: {loc['is_active']}")
        
        print("\n--- Data Value Check (Sample Timestamp) ---")
        # Get a common timestamp
        ts = await conn.fetchval("SELECT forecast_for_datetime FROM weather_hourly_window WHERE location_name = 'Lahore' LIMIT 1")
        if ts:
            values = await conn.fetch("SELECT location_name, temp_c, latitude, longitude FROM weather_hourly_window WHERE forecast_for_datetime = $1", ts)
            for v in values:
                print(f"{v['location_name']} | Temp: {v['temp_c']} | Lat/Lon: {v['latitude']}/{v['longitude']}")
        else:
            print("No timestamps found.")
        
        print("\n--- Daily ID Check ---")
        daily_ids = await conn.fetch("SELECT location_name, location_id, count(*) FROM weather_daily_summaries GROUP BY location_name, location_id")
        for d in daily_ids:
            print(f"Name: {d['location_name']} | ID in Weather: {d['location_id']} | Count: {d['count']}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_db())
