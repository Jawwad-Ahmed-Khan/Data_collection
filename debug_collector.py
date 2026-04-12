import asyncio
import httpx
from app.main import app, lifespan
import app.main as m

async def debug_collector():
    async with lifespan(app):
        print("Running OpenMeteo collection...")
        result = await m._openmeteo_collector.collect()
        print(f"Total Locations Targeted: {result.get('locations_targeted')}")
        print(f"Total Daily Rows: {result.get('daily_rows')}")
        print(f"Total Hourly Rows: {result.get('hourly_rows')}")
        
        # Check individual location counts in DB again to be super sure
        conn = m._db_pool.get_connection() # This might not work depending on implementation
        # Actually use the repo
        locations = await m._ref_repo.get_active_locations()
        for loc in locations:
             # We can't easily check individual upsert counts from here without looking at the logs
             pass

if __name__ == "__main__":
    asyncio.run(debug_collector())
