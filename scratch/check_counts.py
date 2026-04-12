import asyncio
import asyncpg
from app.core.config import get_settings

async def check_counts():
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_dsn, statement_cache_size=0)
    try:
        tables = [
            "seismic_events",
            "flood_gauge_registry",
            "flood_gauge_current",
            "flood_gauge_forecasts",
            "weather_hourly_window",
            "weather_daily_summaries",
            "pakistan_locations",
            "pakistan_infrastructure",
            "threshold_breach_log"
        ]
        
        for table in tables:
            count = await conn.fetchval(f"SELECT count(*) FROM {table}")
            print(f"{table}: {count}")
            
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_counts())
