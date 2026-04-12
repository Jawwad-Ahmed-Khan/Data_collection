import asyncio
import asyncpg
from app.core.config import get_settings

async def check_registry():
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_dsn, statement_cache_size=0)
    try:
        print("--- Flood Gauge Registry ---")
        gauges = await conn.fetch("SELECT gauge_name, google_gauge_id, district, province, nearest_location_id FROM flood_gauge_registry")
        for g in gauges:
            loc_name = "None"
            if g['nearest_location_id']:
                loc_name = await conn.fetchval("SELECT location_name FROM pakistan_locations WHERE location_id = $1", g['nearest_location_id'])
            print(f"Gauge: {g['gauge_name']} | Nearest Loc: {loc_name} | District: {g['district']}")
            
        print("\n--- Pakistan Locations ---")
        locs = await conn.fetch("SELECT location_id, location_name FROM pakistan_locations")
        for l in locs:
            print(f"Location: {l['location_name']} (ID: {l['location_id']})")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_registry())
