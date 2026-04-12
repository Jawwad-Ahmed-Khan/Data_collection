import asyncio
import asyncpg
import os

from app.core.config import get_settings

async def seed_apis():
    settings = get_settings()
    dsn = settings.database_dsn
    print(f"Connecting to database (Project: {settings.collection_db_user})...")
    
    # We must use statement_cache_size=0 for Supabase PgBouncer compatibility
    conn = await asyncpg.connect(dsn, statement_cache_size=0)
    
    seeds = [
        {
            "api_name": "usgs",
            "display_name": "USGS Earthquake Hazards Program",
            "base_url": "https://earthquake.usgs.gov/fdsnws/event/1/query",
            "documentation_url": "https://earthquake.usgs.gov/fdsnws/event/1/",
            "max_requests_per_minute": 60,
            "max_requests_per_day": 10000,
            "min_delay_between_calls_ms": 300,
        },
        {
            "api_name": "open_meteo",
            "display_name": "Open-Meteo Weather Forecast API",
            "base_url": "https://api.open-meteo.com/v1/forecast",
            "documentation_url": "https://open-meteo.com/en/docs",
            "max_requests_per_minute": 40,
            "max_requests_per_day": 10000,
            "min_delay_between_calls_ms": 1000,
        },
        {
            "api_name": "google_flood_hub",
            "display_name": "Google Flood Hub API",
            "base_url": "https://floodhub.googleapis.com/v1",
            "documentation_url": "https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_Research_open-buildings_v3",
            "max_requests_per_minute": 60,
            "max_requests_per_day": 10000,
            "min_delay_between_calls_ms": 500,
        }
    ]

    try:
        for seed in seeds:
            print(f"Inserting {seed['api_name']}...")
            await conn.execute("""
                INSERT INTO api_registry 
                    (api_name, display_name, base_url, documentation_url, 
                     max_requests_per_minute, max_requests_per_day, min_delay_between_calls_ms)
                VALUES 
                    ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (api_name) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    base_url = EXCLUDED.base_url,
                    documentation_url = EXCLUDED.documentation_url,
                    max_requests_per_minute = EXCLUDED.max_requests_per_minute,
                    max_requests_per_day = EXCLUDED.max_requests_per_day,
                    min_delay_between_calls_ms = EXCLUDED.min_delay_between_calls_ms;
            """, 
            seed['api_name'], seed['display_name'], seed['base_url'], 
            seed['documentation_url'], seed['max_requests_per_minute'], 
            seed['max_requests_per_day'], seed['min_delay_between_calls_ms'])
            
        print("API Registry seeded successfully!")
        
        count = await conn.fetchval("SELECT count(*) FROM api_registry")
        print(f"Total APIs in registry: {count}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(seed_apis())
