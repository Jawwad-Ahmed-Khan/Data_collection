import asyncio
import asyncpg
from datetime import datetime
import os
from app.core.config import get_settings

async def debug_weather():
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_dsn, statement_cache_size=0)
    try:
        now = datetime.now()
        print(f"Current local time: {now}")
        
        # Check some records in hourly window
        rows = await conn.fetch("SELECT location_name, forecast_for_datetime FROM weather_hourly_window LIMIT 5")
        for row in rows:
            print(f"Record: {row['location_name']} at {row['forecast_for_datetime']} (Type: {type(row['forecast_for_datetime'])})")
            
        # Check current hour records
        sql = """
            SELECT count(*) 
            FROM weather_hourly_window 
            WHERE forecast_for_datetime >= date_trunc('hour', now())
              AND forecast_for_datetime <  date_trunc('hour', now()) + interval '1 hour'
        """
        current_hour_count = await conn.fetchval(sql)
        print(f"Current hour records in table (using DB now()): {current_hour_count}")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(debug_weather())
