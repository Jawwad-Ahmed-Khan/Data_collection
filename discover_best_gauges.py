import asyncio
import httpx
import os
import json
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GOOGLE_FLOOD_HUB_API_KEY")
BASE_URL = "https://floodforecasting.googleapis.com/v1"

async def discover_gauges():
    url = f"{BASE_URL}/gauges:searchGaugesByArea"
    params = {"key": API_KEY}
    
    # Body as specified by user
    body = {
        "regionCode": "PK",
        "pageSize": 20,
        "includeNonQualityVerified": True
    }
    
    print(f"Discovering gauges in Pakistan via POST {url}...")
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, params=params, json=body)
        if resp.status_code != 200:
            print(f"FAILED: {resp.text}")
            return
            
        data = resp.json()
        gauges = data.get("gauges", [])
        print(f"Found {len(gauges)} gauges.")
        
        active_gauges = []
        for g in gauges:
            gid = g.get("gaugeId")
            name = g.get("name", "Unnamed")
            loc = g.get("location", {})
            lat = loc.get("latitude")
            lon = loc.get("longitude")
            
            # Check for actual data
            q_url = f"{BASE_URL}/gauges:queryGaugeForecasts"
            q_resp = await client.get(q_url, params={"key": API_KEY, "gaugeIds": gid})
            if q_resp.status_code == 200:
                q_data = q_resp.json()
                f_map = q_data.get("forecasts", {})
                inner_val = f_map.get(gid, {})
                f_sets = inner_val.get("forecasts", [])
                points = 0
                if f_sets:
                    # Check both timed values and ranges
                    points = len(f_sets[0].get("forecastTimedValues", []))
                    if points == 0:
                        points = len(f_sets[0].get("forecastRanges", []))
                
                print(f"  {gid}: {points} points ({name}) at {lat}, {lon}")
                if points > 0:
                    active_gauges.append({
                        "google_gauge_id": gid,
                        "gauge_name": name,
                        "lat": lat,
                        "lon": lon
                    })
        
        # Save to JSON for the update script
        with open("active_gauges.json", "w") as f:
            json.dump(active_gauges, f, indent=2)
        print(f"\nSaved {len(active_gauges)} active gauges to active_gauges.json")

if __name__ == "__main__":
    asyncio.run(discover_gauges())
