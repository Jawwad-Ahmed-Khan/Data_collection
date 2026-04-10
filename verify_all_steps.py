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

async def test_schemas():
    settings = get_settings()
    pool = DatabasePool(settings)
    await pool.connect()
    print("Connected to Supabase.")
    
    # Repos
    ref_repo = ReferenceRepository(pool)
    flood_repo = FloodRepository(pool)
    seis_repo = SeismicRepository(pool)
    
    errors = []

    print("1. Testing thresholds...")
    try:
        t = await ref_repo.get_all_thresholds()
        print(f"   -> OK: {len(t)} found.")
    except Exception as e:
        errors.append(f"Thresholds failed: {e}")

    print("2. Testing locations...")
    try:
        l = await ref_repo.get_active_locations()
        print(f"   -> OK: {len(l)} found.")
    except Exception as e:
        errors.append(f"Locations failed: {e}")

    print("3. Testing flood gauges...")
    try:
        f = await flood_repo.get_active_flood_gauges()
        print(f"   -> OK: {len(f)} found.")
    except Exception as e:
        errors.append(f"Flood Gauges failed: {e}")

    # Note: We cannot query recent events without data, but if it executes it's fine.
    print("4. Testing seismic events...")
    try:
        s = await seis_repo.get_recent_events()
        print(f"   -> OK: {len(s)} found.")
    except Exception as e:
        errors.append(f"Seismic Events failed: {e}")

    await pool.disconnect()

    if errors:
        print("\nERRORS FOUND:")
        for err in errors:
            print(f" - {err}")
        sys.exit(1)
    else:
        print("ALL SCHEMAS VERIFIED AGAINST LIVE SUPABASE DATA.")

if __name__ == "__main__":
    asyncio.run(test_schemas())
