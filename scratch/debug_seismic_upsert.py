import asyncio
import asyncpg
import uuid
from datetime import datetime
from app.core.config import get_settings
from app.database.queries.seismic_queries import UPSERT_SEISMIC_EVENT

async def debug_query():
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_dsn, statement_cache_size=0)
    
    try:
        print("Testing UPSERT_SEISMIC_EVENT with explicit parameters...")
        # 33 parameters
        params = [
            uuid.uuid4(),           # $1: event_id
            "test_event_id_" + str(uuid.uuid4())[:8], # $2: usgs_event_id
            "http://test.url",      # $3
            5.5,                    # $4: magnitude
            "mw",                   # $5
            "moderate",             # $6
            10.0,                   # $7: depth_km
            "shallow",              # $8
            33.9,                   # $9: latitude
            72.3,                   # $10: longitude
            "Test Place, Pakistan", # $11: usgs_place (VARCHAR)
            "Nowshera",             # $12: district
            "Khyber Pakhtunkhwa",   # $13: province (pk_province)
            None,                   # $14: nearest_location_id
            1.5,                    # $15: distance
            0,                      # $16
            None,                   # $17
            None,                   # $18
            False,                  # $19
            "green",                # $20
            100,                    # $21
            10,                     # $22
            30.0,                   # $23
            0.5,                    # $24
            "automatic",            # $25
            ["us"],                 # $26
            datetime.now(),         # $27
            datetime.now(),         # $28
            False,                  # $29
            None,                   # $30
            None,                   # $31
            None,                   # $32: cycle_id
            {}                      # $33: raw_api_response
        ]
        
        import json
        params[32] = json.dumps(params[32])
        row = await conn.fetchrow(UPSERT_SEISMIC_EVENT, *params)
        print("Success! Event ID:", row['event_id'])
        
    except Exception as e:
        print("FAILED:", str(e))
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(debug_query())
