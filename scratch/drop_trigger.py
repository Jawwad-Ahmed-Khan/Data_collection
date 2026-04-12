import asyncio
import asyncpg
from app.core.config import get_settings

async def fix():
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_dsn, ssl="require")
    try:
        print("Dropping trigger...")
        await conn.execute("DROP TRIGGER IF EXISTS trg_seismic_coordinates ON seismic_events;")
        print("Trigger dropped.")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(fix())
