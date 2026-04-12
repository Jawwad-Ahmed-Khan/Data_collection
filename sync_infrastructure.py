"""
ClimaSync Collection Service — Infrastructure Sync Tool

Synchronizes the pakistan_infrastructure table with real-world data from OpenStreetMap.
Iterates through all active locations and pulls assets within a 20km radius.
"""

import asyncio
import asyncpg
import time
from app.core.config import get_settings
from app.services.osm_service import OSMService
from app.core.logger import get_logger

logger = get_logger(__name__)

async def sync_infrastructure():
    settings = get_settings()
    dsn = settings.database_dsn
    osm_service = OSMService(radius_km=10)
    
    print("Connecting to database...")
    conn = await asyncpg.connect(dsn, statement_cache_size=0)
    
    try:
        # 1. Fetch all active locations
        locations = await conn.fetch("SELECT location_id, location_name, latitude, longitude FROM pakistan_locations WHERE is_active = TRUE")
        print(f"Found {len(locations)} active locations to sync infrastructure for.")
        
        total_upserted = 0
        
        for loc in locations:
            loc_id = loc['location_id']
            loc_name = loc['location_name']
            lat = float(loc['latitude'])
            lon = float(loc['longitude'])
            
            print(f"\n--- Syncing Infrastructure for {loc_name} ---")
            
            # 2. Query OSM
            elements = osm_service.query_infrastructure(lat, lon)
            
            # 3. Process and UPSERT
            loc_count = 0
            for el in elements:
                asset = osm_service.map_to_internal(el)
                if not asset:
                    continue
                
                try:
                    await conn.execute("""
                        INSERT INTO pakistan_infrastructure (
                            location_id, asset_name, asset_type, latitude, longitude,
                            coordinates, district, is_critical, external_id,
                            vulnerability_level, updated_at
                        ) VALUES (
                            $1, $2, $3::asset_type, $4::numeric, $5::numeric,
                            ST_SetSRID(ST_MakePoint($5::float8, $4::float8), 4326), $6, $7, $8, 
                            $9::vulnerability_level, NOW()
                        )
                        ON CONFLICT (external_id) DO UPDATE SET
                            asset_name = EXCLUDED.asset_name,
                            asset_type = EXCLUDED.asset_type,
                            latitude = EXCLUDED.latitude,
                            longitude = EXCLUDED.longitude,
                            coordinates = EXCLUDED.coordinates,
                            is_critical = EXCLUDED.is_critical,
                            updated_at = NOW();
                    """, 
                    loc_id, asset['asset_name'], asset['asset_type'], 
                    asset['latitude'], asset['longitude'], loc_name,
                    asset['is_critical'], asset['external_id'], asset['vulnerability_level'])
                    
                    loc_count += 1
                except Exception as e:
                    logger.error("Failed to upsert asset %s: %s", asset['asset_name'], str(e))
            
            print(f"Successfully synced {loc_count} assets for {loc_name}.")
            total_upserted += loc_count
            
            # Respect Overpass rate limits (slight pause)
            await asyncio.sleep(2)

        print(f"\nInfrastructure sync complete! Total assets processed: {total_upserted}")

    finally:
        await conn.close()
        print("Database connection closed.")

if __name__ == "__main__":
    asyncio.run(sync_infrastructure())
