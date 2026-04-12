import asyncio
from app.core.config import get_settings
from app.database.connection import DatabasePool

# Selected Gauges based on proximity to cities
GAUGES_TO_INSERT = [
    # City: Faisalabad
    {"id": "hybas_4121420920", "name": "Chenab River near Faisalabad", "city": "Faisalabad", "lat": 31.3729, "lon": 72.2604},
    # City: Hyderabad
    {"id": "hybas_4120897930", "name": "Indus River near Hyderabad", "city": "Hyderabad", "lat": 25.8604, "lon": 68.7896},
    # City: Islamabad
    {"id": "hybas_4120689260", "name": "Soan River near Islamabad", "city": "Islamabad", "lat": 33.5523, "lon": 73.1017},
    # City: Karachi
    {"id": "hybas_4120918740", "name": "Malir River near Karachi", "city": "Karachi", "lat": 24.9604, "lon": 67.1438},
    # City: Lahore
    {"id": "hybas_4121417930", "name": "Ravi River near Lahore", "city": "Lahore", "lat": 31.6063, "lon": 73.3188},
    # City: Multan (Indus)
    {"id": "hybas_4120716860", "name": "Indus River near Multan", "city": "Multan", "lat": 30.7063, "lon": 70.8313},
    # City: Peshawar
    {"id": "hybas_4120655420", "name": "Kabul River near Peshawar", "city": "Peshawar", "lat": 34.2563, "lon": 71.0188},
    # City: Quetta (Virtual Basin)
    {"id": "hybas_4121440160", "name": "Basin near Quetta", "city": "Quetta", "lat": 31.4854, "lon": 67.3188},
]

async def update_registry():
    settings = get_settings()
    db = DatabasePool(settings)
    await db.connect()
    
    try:
        # 1. Clear existing registry
        print("Clearing existing flood_gauge_registry...")
        await db.execute("DELETE FROM flood_gauge_registry")
        
        # 2. Get location mappings
        locations = await db.fetch_many("SELECT location_id, location_name FROM pakistan_locations")
        loc_map = {l["location_name"]: l["location_id"] for l in locations}
        
        # 3. Insert real gauges
        print(f"Inserting {len(GAUGES_TO_INSERT)} real gauges...")
        
        args_list = []
        for g in GAUGES_TO_INSERT:
            loc_id = loc_map.get(g["city"])
            if not loc_id:
                print(f"Skipping {g['name']} - city {g['city']} not found in DB")
                continue
            
            # Extract river name from gauge name if possible
            river = g["name"].split(" near ")[0] if " near " in g["name"] else "Unknown River"

            args_list.append((
                g["id"],      # google_gauge_id
                g["name"],    # gauge_name
                river,        # river_name (MANDATORY)
                loc_id,       # nearest_location_id
                g["lat"],     # latitude
                g["lon"]      # longitude
            ))
        
        insert_query = """
            INSERT INTO flood_gauge_registry 
                (google_gauge_id, gauge_name, river_name, nearest_location_id, latitude, longitude, coordinates)
            VALUES 
                ($1, $2, $3, $4, $5::numeric, $6::numeric, ST_SetSRID(ST_MakePoint($6::float, $5::float), 4326)::geography)
        """
        await db.execute_many(insert_query, args_list)
        print("Successfully updated flood_gauge_registry with real data.")
        
    finally:
        await db.disconnect()

if __name__ == "__main__":
    asyncio.run(update_registry())
