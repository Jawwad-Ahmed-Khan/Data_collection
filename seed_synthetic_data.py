import asyncio
import asyncpg
from app.core.config import get_settings
from uuid import uuid4

async def seed_synthetic_data():
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_dsn, statement_cache_size=0)
    
    try:
        print("Fetching existing locations...")
        locs = await conn.fetch("SELECT location_id, location_key, location_name FROM pakistan_locations")
        loc_map = {l['location_name']: l['location_id'] for l in locs}
        
        # 1. Flood Gauge Registry
        print("Seeding Flood Gauge Registry...")
        gauges = [
            # Real Google Flood Hub IDs for Pakistan
            ("Kabul River", "Nowshera", "hybas_4120647980", "Nowshera Gauge", 33.91458, 72.28542, "khyber_pakhtunkhwa", 280.0, 285.0, 290.0),
            ("Malir River", "Karachi", "hybas_4120033770", "Karachi Malir Gauge", 24.80208, 67.08125, "sindh", 12.0, 15.0, 18.0)
        ]
        
        for g in gauges:
            river, loc_name, gid, name, lat, lon, prov, warn, danger, ext = g
            loc_id = loc_map.get(loc_name)
            if not loc_id:
                continue
                
            await conn.execute("""
                INSERT INTO flood_gauge_registry (
                    google_gauge_id, gauge_name, river_name, coordinates, latitude, longitude,
                    province, district, nearest_location_id, warning_level_m, danger_level_m, extreme_level_m, poll_priority
                ) VALUES (
                    $1, $2, $3, ST_SetSRID(ST_MakePoint($5, $4), 4326), $4, $5,
                    $11, $6, $7, $8, $9, $10, 'high'
                ) ON CONFLICT (google_gauge_id) DO UPDATE SET
                    gauge_name = EXCLUDED.gauge_name,
                    river_name = EXCLUDED.river_name,
                    province = EXCLUDED.province,
                    district = EXCLUDED.district;
            """, gid, name, river, lat, lon, loc_name, loc_id, warn, danger, ext, prov)
        
        # 2. Pakistan Infrastructure
        print("Seeding Pakistan Infrastructure...")
        infrastructure_assets = [
            # Lahore (Punjab)
            ("Jinnah Hospital Lahore", "hospital", "Lahore", 31.4883, 74.2934, 1500, "beds", "very_high", True),
            ("Lahore General Hospital", "hospital", "Lahore", 31.4633, 74.3421, 1000, "beds", "high", False),
            ("Ravi Bridge", "bridge", "Lahore", 31.6033, 74.2982, 50000, "vehicles/day", "critical", False),
            ("Edhi Evacuation Center", "evacuation_center", "Lahore", 31.5497, 74.3436, 10000, "persons", "moderate", True),
            
            # Karachi (Sindh)
            ("Aga Khan University Hospital", "hospital", "Karachi", 24.8920, 67.0734, 721, "beds", "very_high", True),
            ("Jinnah Postgraduate Medical Centre", "hospital", "Karachi", 24.8524, 67.0427, 2200, "beds", "critical", False),
            ("NIPA Evacuation Center", "evacuation_center", "Karachi", 24.9180, 67.0971, 15000, "persons", "high", True),
            ("Lyari Expressway", "bridge", "Karachi", 24.8943, 67.0016, 100000, "vehicles/day", "very_high", False),
            
            # Islamabad (ICT)
            ("Pakistan Institute of Medical Sciences (PIMS)", "hospital", "Islamabad", 33.7042, 73.0487, 1200, "beds", "high", True),
            ("Rawal Dam", "dam", "Islamabad", 33.7431, 73.1256, 47500, "acre-ft", "moderate", True),
            ("Faizabad Interchange", "bridge", "Islamabad", 33.6601, 73.0784, 150000, "vehicles/day", "very_high", True)
        ]
        
        # Clean infrastructure first to avoid duplicates since we have no unique key other than asset_id
        await conn.execute("TRUNCATE TABLE pakistan_infrastructure CASCADE;")
        
        for asset in infrastructure_assets:
            name, atype, loc_name, lat, lon, capacity, unit, vuln, is_crit = asset
            loc_id = loc_map.get(loc_name)
            if not loc_id:
                continue
                
            await conn.execute("""
                INSERT INTO pakistan_infrastructure (
                    location_id, asset_name, asset_type, coordinates, latitude, longitude,
                    district, capacity, capacity_unit, vulnerability_level, is_critical
                ) VALUES (
                    $1, $2, $3::asset_type, ST_SetSRID(ST_MakePoint($5, $4), 4326), $4, $5,
                    $6, $7, $8, $9::vulnerability_level, $10
                );
            """, loc_id, name, atype, lat, lon, loc_name, capacity, unit, vuln, is_crit)
            
        print("Data seeded successfully!")
        
        infra_count = await conn.fetchval("SELECT count(*) FROM pakistan_infrastructure")
        gauge_count = await conn.fetchval("SELECT count(*) FROM flood_gauge_registry")
        print(f"Infrastructure count: {infra_count}")
        print(f"Flood Gauge count: {gauge_count}")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(seed_synthetic_data())
