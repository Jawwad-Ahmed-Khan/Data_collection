import asyncio
from app.main import lifespan, app
import app.main as m
import sys
import os

os.environ.setdefault("PYTHONUTF8", "1")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
# 

async def run_extraction():
    print("Booting up ClimaSync Data Extraction Engine...")
    
    # We use the FastAPI lifespan context manager which cleanly initializes
    # the database, all collectors, algorithms, and caches!
    async with lifespan(app):
        print("\n" + "="*50)
        print("FORCING MANUAL GOOGLE FLOOD HUB EXTRACTION CYCLE")
        print("="*50)
        
        flood_current_result = await m._floodhub_collector.collect_current_readings()
        flood_forecast_result = await m._floodhub_collector.collect_forecasts()
        
        print("\n" + "="*50)
        print("FORCING MANUAL USGS SEISMIC EXTRACTION CYCLE")
        print("="*50)
        
        usgs_result = await m._usgs_collector.collect()
        
        print("\n" + "="*50)
        print("FORCING MANUAL OPEN-METEO WEATHER EXTRACTION CYCLE")
        print("="*50)
        
        openmeteo_result = await m._openmeteo_collector.collect()
        
        print("\n" + "="*50)
        print("EXTRACTION SUMMARY")
        print("="*50)
        print(f"USGS Cycle Outcome: {usgs_result.get('status')}")
        print(f"USGS Records Upserted: {usgs_result.get('rows_upserted', 0)}")
        print(f"USGS Breaches Triggered: {usgs_result.get('breaches_triggered', 0)}")
        print(f"OpenMeteo Outcome: {openmeteo_result.get('status')}")
        print(f"OpenMeteo Records Upserted: {openmeteo_result.get('hourly_rows', 0) + openmeteo_result.get('daily_rows', 0)}")
        print(f"OpenMeteo Target Locations: {openmeteo_result.get('locations_targeted', 0)}")
        print(f"OpenMeteo Breaches Detected: {openmeteo_result.get('breaches_detected', 0)}")

if __name__ == "__main__":
    asyncio.run(run_extraction())
