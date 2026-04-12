import asyncio
import asyncpg
from app.core.config import get_settings

async def fix():
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_dsn, ssl="require")
    try:
        print("Creating trigger function...")
        await conn.execute("""
            CREATE OR REPLACE FUNCTION compute_seismic_coordinates()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.coordinates := ST_SetSRID(ST_MakePoint(NEW.longitude, NEW.latitude), 4326);
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """)
        print("Creating trigger...")
        await conn.execute("""
            DROP TRIGGER IF EXISTS trg_seismic_coordinates ON seismic_events;
            CREATE TRIGGER trg_seismic_coordinates
            BEFORE INSERT OR UPDATE ON seismic_events
            FOR EACH ROW
            EXECUTE FUNCTION compute_seismic_coordinates();
        """)
        print("Trigger re-enabled.")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(fix())
