import asyncio
from app.main import app, lifespan
import app.main as m

async def test_repo():
    async with lifespan(app):
        print("Testing ReferenceRepository.get_active_locations()...")
        try:
            locations = await m._ref_repo.get_active_locations()
            print(f"Success! Found {len(locations)} locations.")
            for loc in locations:
                print(f" - {loc.location_name}")
        except Exception as e:
            print(f"Failure! Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_repo())
