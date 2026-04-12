import asyncio
import asyncpg
from app.core.config import get_settings
import subprocess

async def clean_and_run():
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_dsn, statement_cache_size=0)
    try:
        print("Cleaning weather tables...")
        await conn.execute("DELETE FROM weather_hourly_window")
        await conn.execute("DELETE FROM weather_daily_summaries")
        print("Tables cleaned.")
    finally:
        await conn.close()

    print("Running oneshot extraction...")
    # Run oneshot
    process = subprocess.run(["python", "run_oneshot.py"], capture_output=True, text=True)
    print(process.stdout)
    if process.stderr:
        print("Errors:")
        print(process.stderr)

    # Check results
    conn = await asyncpg.connect(settings.database_dsn, statement_cache_size=0)
    try:
        print("\n--- NEW Counts ---")
        hourly = await conn.fetch("SELECT location_name, count(*) FROM weather_hourly_window GROUP BY location_name")
        for h in hourly:
            print(f"Hourly - {h['location_name']}: {h['count']}")
            
        daily = await conn.fetch("SELECT location_name, count(*) FROM weather_daily_summaries GROUP BY location_name")
        for d in daily:
            print(f"Daily - {d['location_name']}: {d['count']}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(clean_and_run())
