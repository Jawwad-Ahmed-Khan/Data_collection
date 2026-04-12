import asyncio
import asyncpg
from app.core.config import get_settings

async def inspect_db():
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_dsn, statement_cache_size=0)
    try:
        print("--- Tables ---")
        tables = await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'")
        for t in tables:
            print(t['table_name'])
            
        print("\n--- Views ---")
        views = await conn.fetch("SELECT viewname FROM pg_catalog.pg_views WHERE schemaname = 'public'")
        for v in views:
            print(v['viewname'])
            
        print("\n--- Current Weather View Check ---")
        try:
            row_count = await conn.fetchval("SELECT count(*) FROM current_weather_per_location")
            print(f"current_weather_per_location count: {row_count}")
            rows = await conn.fetch("SELECT location_name FROM current_weather_per_location")
            for r in rows:
                print(f"  - {r['location_name']}")
        except Exception as e:
            print(f"Could not check current_weather_per_location: {e}")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(inspect_db())
