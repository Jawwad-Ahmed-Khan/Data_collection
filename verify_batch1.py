import asyncio
import sys

try:
    from app.core.config import get_settings
    from app.database.connection import DatabasePool
    
    # Check queries syntax by importing them
    import app.database.queries.seismic_queries
    import app.database.queries.weather_queries
    import app.database.queries.flood_queries
    import app.database.queries.breach_queries
    import app.database.queries.cycle_queries
    import app.database.queries.reference_queries
    
    print("ALL IMPORTS SUCCESSFUL. NO SYNTAX ERRORS.")
    
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)

async def check_db():
    settings = get_settings()
    pool = DatabasePool(settings)
    try:
        await pool.connect()
        print("DATABASE CONNECTIVITY SUCCESSFUL.")
        await pool.disconnect()
    except Exception as e:
        print(f"DATABASE CONNECTION SKIPPED OR FAILED (Expected if no local DB running): {e}")

if __name__ == "__main__":
    asyncio.run(check_db())
