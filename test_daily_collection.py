import asyncio
import httpx
from app.main import app, lifespan
import app.main as m
from app.models.reference_models import PakistanLocation

async def test_daily_only():
    async with lifespan(app):
        print("Testing Daily Data Collection for all active locations...")
        locations = await m._ref_repo.get_active_locations()
        print(f"Found {len(locations)} active locations.")
        
        for loc in locations:
            print(f"\nProcessing {loc.location_name}...")
            daily_params = m._openmeteo_service.build_daily_params(loc.latitude, loc.longitude)
            # Use the base collector's client
            response = await m._openmeteo_collector.get(settings.openmeteo_base_url, params=daily_params)
            data = response.json()
            summaries = m._openmeteo_service.parse_daily(data, loc)
            print(f"  Parsed {len(summaries)} daily summaries.")
            
            for s in summaries:
                try:
                    await m._weather_repo.upsert_daily(s)
                    print(f"  ✓ Upserted {s.summary_date}")
                except Exception as e:
                    print(f"  ✗ Failed upsert for {s.summary_date}: {e}")

if __name__ == "__main__":
    # We need to import settings to get the URL
    from app.core.config import get_settings
    settings = get_settings()
    asyncio.run(test_daily_only())
