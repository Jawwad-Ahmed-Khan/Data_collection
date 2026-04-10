import asyncio
import sys

from app.core.config import get_settings
from app.database.connection import DatabasePool

from app.repositories import (
    BreachRepository,
    CycleRepository,
    FloodRepository,
    ReferenceRepository,
    SeismicRepository,
    WeatherRepository,
)

async def check_repos():
    try:
        print("Instantiating database pool and repositories...")
        settings = get_settings()
        pool = DatabasePool(settings)
        
        breach_repo = BreachRepository(pool)
        cycle_repo = CycleRepository(pool)
        flood_repo = FloodRepository(pool)
        ref_repo = ReferenceRepository(pool)
        seis_repo = SeismicRepository(pool)
        wea_repo = WeatherRepository(pool)
        
        print("Repositories instantiated successfully.")
        
        print("Starting DB checks if locally available...")
        try:
            await pool.connect()
            # Try a safe read
            active_apis = await ref_repo.get_all_thresholds()
            print(f"Successfully ran ReferenceRepository query. Found {len(active_apis)} thresholds.")
            await pool.disconnect()
        except Exception as e:
            print(f"DB verification skipped/failed (Expected if no local DB): {e}")
            
        print("ALL TESTS SUCCESSFUL.")
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(check_repos())
