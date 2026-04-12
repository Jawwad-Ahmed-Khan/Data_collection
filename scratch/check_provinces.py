import asyncio
import asyncpg
from app.core.config import get_settings

async def check():
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_dsn, statement_cache_size=0)
    try:
        rows = await conn.fetch("SELECT location_name, province FROM pakistan_locations")
        for row in rows:
            print(f"{row['location_name']}: {row['province']}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check())
