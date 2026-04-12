import asyncio
import json
import uuid
from app.database.connection import DatabasePool
from app.core.config import get_settings

async def update_registry():
    # Load discovered gauges
    try:
        with open("active_gauges.json", "r") as f:
            gauges = json.load(f)
    except FileNotFoundError:
        print("active_gauges.json not found.")
        return
    
    if not gauges:
        print("No active gauges found in JSON.")
        return

    # Select top 8 or specific high-confidence ones
    selected = gauges[:8]

    settings = get_settings()
    db_pool = DatabasePool(settings=settings)
    await db_pool.connect()

    try:
        print("Clearing old registry entries...")
        await db_pool.execute("DELETE FROM public.flood_gauge_registry WHERE api_source = 'google_flood_hub'")
        
        # Mapping to better names/metadata
        # (Usually this would come from the API, but we'll use our curated list logic)
        stations = [
            ("Indus River at Tarbela", "Indus", "Haripur", "KPK"),
            ("Indus River near Multan", "Indus", "Multan", "Punjab"),
            ("Kabul River near Peshawar", "Kabul", "Peshawar", "KPK"),
            ("Chenab River near Faisalabad", "Chenab", "Faisalabad", "Punjab"),
            ("Ravi River near Lahore", "Ravi", "Lahore", "Punjab"),
            ("Malir River near Karachi", "Malir", "Karachi", "Sindh"),
            ("Indus River near Hyderabad", "Indus", "Hyderabad", "Sindh"),
            ("Basin near Quetta", "Coastal", "Quetta", "Balochistan")
        ]

        for i, g in enumerate(selected):
            gauge_uuid = str(uuid.uuid4())
            name, river, district, province = stations[i] if i < len(stations) else (f"Gauge {i}", "System", "Various", "Pakistan")
            
            print(f"Adding gauge: {g['google_gauge_id']} | {name}")
            await db_pool.execute(
                """
                INSERT INTO public.flood_gauge_registry (
                    gauge_id, google_gauge_id, gauge_name, river_name, river_system,
                    latitude, longitude, district, province, api_source, is_active
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """,
                gauge_uuid, 
                g["google_gauge_id"], 
                name, 
                river, 
                "Indus Basin",
                float(g["lat"]), 
                float(g["lon"]), 
                district, 
                province, 
                "google_flood_hub", 
                True
            )
        
        print(f"\nSuccessfully updated registry with {len(selected)} live gauges.")

    finally:
        await db_pool.disconnect()

if __name__ == "__main__":
    asyncio.run(update_registry())
