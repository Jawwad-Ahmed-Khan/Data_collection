import asyncio
import asyncpg
from app.core.config import get_settings

async def inspect():
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_dsn, ssl="require")
    try:
        rows = await conn.fetch("""
            SELECT column_name, ordinal_position, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'seismic_events' 
            ORDER BY ordinal_position;
        """)
        for r in rows:
            print(f"{r['ordinal_position']}: {r['column_name']} ({r['data_type']})")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(inspect())
