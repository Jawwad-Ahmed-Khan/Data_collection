"""
ClimaSync Collection Service — Seed Data Script

Aligned with the official schema provided by the user.
Uses UPSERT (ON CONFLICT DO UPDATE) to append/update data instead of deleting.
"""

import asyncio
import asyncpg
from app.core.config import get_settings

async def seed_data():
    settings = get_settings()
    dsn = settings.database_dsn
    
    print(f"Connecting to database: {settings.collection_db_host}")
    conn = await asyncpg.connect(dsn, statement_cache_size=0)
    
    try:
        # location_key, name, local_name, tier, district, division, province, lat, lon, seismic_zone, population, flood_zone, heat_zone, infra_quality
        locations = [
            ("lahore_31.5497_74.3436", "Lahore", "لاہور", "tier_1_provincial_capital", "Lahore", "Lahore", "punjab", 31.5497, 74.3436, "II", 11126285, "zone_1_low", "zone_3_high", "moderate"),
            ("karachi_24.8607_67.0011", "Karachi", "کراچی", "tier_1_provincial_capital", "Karachi", "Karachi", "sindh", 24.8607, 67.0011, "III", 16051521, "zone_2_moderate", "zone_5_critical", "low"),
            ("islamabad_33.6844_73.0479", "Islamabad", "اسلام آباد", "tier_1_provincial_capital", "Islamabad", "Islamabad", "islamabad_capital_territory", 33.6844, 73.0479, "III", 1014825, "zone_1_low", "zone_2_moderate", "moderate"),
            ("peshawar_34.0150_71.5249", "Peshawar", "پشاور", "tier_1_provincial_capital", "Peshawar", "Peshawar", "khyber_pakhtunkhwa", 34.0150, 71.5249, "IV", 1970042, "zone_2_moderate", "zone_2_moderate", "moderate"),
            ("quetta_30.1798_66.9750", "Quetta", "کوئٹہ", "tier_1_provincial_capital", "Quetta", "Quetta", "balochistan", 30.1798, 66.9750, "IV", 1001205, "zone_1_low", "zone_3_high", "low"),
            ("multan_30.1575_71.5249", "Multan", "ملتان", "tier_2_district_headquarters", "Multan", "Multan", "punjab", 30.1575, 71.5249, "II", 1871843, "zone_1_low", "zone_4_very_high", "moderate"),
            ("faisalabad_31.4504_73.1350", "Faisalabad", "فیصل آباد", "tier_2_district_headquarters", "Faisalabad", "Faisalabad", "punjab", 31.4504, 73.1350, "II", 3203846, "zone_1_low", "zone_3_high", "moderate"),
            ("hyderabad_25.3960_68.3578", "Hyderabad", "حیدرآباد", "tier_2_district_headquarters", "Hyderabad", "Hyderabad", "sindh", 25.3960, 68.3578, "II", 1734302, "zone_2_moderate", "zone_4_very_high", "low"),
        ]
        
        thresholds = [
            ("earthquake", "magnitude", "above", 4.0, 5.0, 6.5, 7.5, "National Earthquake Threshold", "magnitude"),
            ("heatwave", "temp_max_c", "above", 40.0, 42.0, 45.0, 48.0, "National Heatwave Threshold", "C"),
            ("heavy_rain", "precip_24h_mm", "above", 40.0, 75.0, 100.0, 150.0, "National Rain Threshold", "mm"),
            ("cyclone", "wind_gusts_kmh", "above", 60.0, 90.0, 120.0, 150.0, "National Wind Threshold", "km/h"),
        ]

        print("\n--- Upserting Pakistan Locations ---")
        for loc in locations:
            key, name, local, tier, dist, div, prov, lat, lon, seismic, pop, f_zone, h_zone, infra = loc
            print(f" - {name} ({key})")
            await conn.execute(f"""
                INSERT INTO pakistan_locations (
                    location_key, location_name, local_name, location_tier, 
                    district, division, province, latitude, longitude,
                    seismic_zone, population, flood_risk_zone, heat_risk_zone,
                    infrastructure_quality, coordinates, is_active
                ) VALUES (
                    $1, $2, $3, $4::location_tier, 
                    $5, $6, $7::pk_province, $8::numeric, $9::numeric, 
                    $10, $11, $12::risk_zone, $13::risk_zone, 
                    $14::vulnerability_level, ST_SetSRID(ST_MakePoint($9::float8, $8::float8), 4326), TRUE
                )
                ON CONFLICT (location_key) DO UPDATE SET
                    location_name = EXCLUDED.location_name,
                    local_name = EXCLUDED.local_name,
                    location_tier = EXCLUDED.location_tier,
                    district = EXCLUDED.district,
                    division = EXCLUDED.division,
                    province = EXCLUDED.province,
                    latitude = EXCLUDED.latitude,
                    longitude = EXCLUDED.longitude,
                    seismic_zone = EXCLUDED.seismic_zone,
                    population = EXCLUDED.population,
                    flood_risk_zone = EXCLUDED.flood_risk_zone,
                    heat_risk_zone = EXCLUDED.heat_risk_zone,
                    infrastructure_quality = EXCLUDED.infrastructure_quality,
                    coordinates = EXCLUDED.coordinates,
                    updated_at = NOW();
            """, key, name, local, tier, dist, div, prov, lat, lon, seismic, pop, f_zone, h_zone, infra)

        print("\n--- Upserting Disaster Thresholds ---")
        for th in thresholds:
            kind, metric, direction, watch, warning, emergency, extreme, desc, unit = th
            print(f" - {kind}: {metric}")
            
            # Using the partial unique index idx_threshold_national: 
            # (disaster_kind, metric_name) WHERE province IS NULL AND district IS NULL AND applies_season IS NULL
            await conn.execute("""
                INSERT INTO disaster_thresholds (
                    disaster_kind, metric_name, breach_direction,
                    watch_threshold, warning_threshold, emergency_threshold, extreme_threshold,
                    description, unit, is_active
                ) VALUES (
                    $1::disaster_kind, $2, $3, 
                    $4, $5, $6, $7, 
                    $8, $9, TRUE
                )
                ON CONFLICT (disaster_kind, metric_name) 
                WHERE province IS NULL AND district IS NULL AND applies_season IS NULL AND is_active = TRUE
                DO UPDATE SET
                    watch_threshold = EXCLUDED.watch_threshold,
                    warning_threshold = EXCLUDED.warning_threshold,
                    emergency_threshold = EXCLUDED.emergency_threshold,
                    extreme_threshold = EXCLUDED.extreme_threshold,
                    updated_at = NOW();
            """, kind, metric, direction, watch, warning, emergency, extreme, desc, unit)

        loc_count = await conn.fetchval("SELECT count(*) FROM pakistan_locations")
        th_count = await conn.fetchval("SELECT count(*) FROM disaster_thresholds")
        print(f"\nSeeding complete. Current state: {loc_count} locations, {th_count} thresholds.")

    finally:
        await conn.close()
        print("Database connection closed.")

if __name__ == "__main__":
    asyncio.run(seed_data())
