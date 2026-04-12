"""
ClimaSync Collection Service — OpenStreetMap (OSM) Service

Dynamically fetches infrastructure assets from OpenStreetMap via Overpass API.
Maps OSM features to internal asset types and marks criticality.
"""

import urllib.request
import json
import time
from typing import Any, Dict, List
from decimal import Decimal
from app.core.logger import get_logger

logger = get_logger(__name__)

class OSMService:
    """Service to interact with OpenStreetMap Overpass API."""

    OVERPASS_URL = "https://overpass-api.de/api/interpreter"
    
    # Mapping of OSM tags to internal asset_type enum
    TAG_MAPPING = {
        "hospital": "hospital",
        "clinic": "basic_health_unit",
        "university": "school",
        "school": "school",
        "college": "school",
        "bridge": "bridge",
        "dam": "dam",
        "barrage": "barrage",
        "station": "power_station", # Often power=station
        "aerodrome": "airport",
    }

    def __init__(self, radius_km: int = 10):
        self.radius_m = radius_km * 1000

    def query_infrastructure(self, lat: float, lon: float) -> List[Dict[str, Any]]:
        """Query Overpass for hospitals, schools, bridges, etc. near coordinates."""
        
        # Optimized Overpass QL Query
        # Use a more targeted search to avoid server timeouts
        query = f"""
        [out:json][timeout:120];
        (
          node["amenity"~"hospital|clinic"](around:{self.radius_m}, {lat}, {lon});
          node["aeroway"="aerodrome"](around:{self.radius_m}, {lat}, {lon});
          node["waterway"~"dam|barrage"](around:{self.radius_m}, {lat}, {lon});
          way["bridge"="yes"](around:{self.radius_m}, {lat}, {lon});
          way["waterway"~"dam|barrage"](around:{self.radius_m}, {lat}, {lon});
        );
        out center;
        """
        
        try:
            logger.info("Querying OSM for assets near %s, %s (radius: %dm)", lat, lon, self.radius_m)
            req = urllib.request.Request(self.OVERPASS_URL, data=query.encode('utf-8'))
            with urllib.request.urlopen(req) as response:
                if response.status != 200:
                    logger.error("OSM Query failed with status %d", response.status)
                    return []
                
                data = json.loads(response.read().decode('utf-8'))
                elements = data.get("elements", [])
                logger.info("Found %d assets for location", len(elements))
                return elements
                
        except Exception as e:
            logger.error("Error querying OSM: %s", str(e))
            return []

    def map_to_internal(self, osm_element: Dict[str, Any]) -> Dict[str, Any] | None:
        """Map an OSM element to our pakistan_infrastructure schema."""
        tags = osm_element.get("tags", {})
        
        # Extract name
        name = tags.get("name") or tags.get("name:en") or tags.get("official_name")
        if not name:
            # Fallback for bridges/dams without names
            type_label = tags.get("amenity") or tags.get("bridge") or tags.get("waterway") or "Asset"
            name = f"{type_label.capitalize()} (OSM {osm_element['id']})"

        # Determine Internal Asset Type
        asset_type = None
        
        # Priority check
        if tags.get("aeroway") == "aerodrome":
            asset_type = "airport"
        elif tags.get("power") == "plant":
            asset_type = "power_station"
        elif tags.get("bridge") == "yes":
            asset_type = "bridge"
        elif tags.get("waterway") in ("dam", "weir", "barrage"):
            asset_type = tags.get("waterway") if tags.get("waterway") in ("dam", "barrage") else "dam"
        elif tags.get("amenity") in self.TAG_MAPPING:
            asset_type = self.TAG_MAPPING[tags.get("amenity")]

        if not asset_type:
            return None

        # Determine Criticality
        is_critical = False
        if asset_type in ("airport", "dam", "barrage", "power_station"):
            is_critical = True
        elif asset_type == "hospital" and tags.get("healthcare") == "hospital":
            is_critical = True

        # Extract Coordinates
        # 'out center' returns 'lat' and 'lon' for ways too
        lat = osm_element.get("lat") or osm_element.get("center", {}).get("lat")
        lon = osm_element.get("lon") or osm_element.get("center", {}).get("lon")
        
        if lat is None or lon is None:
            return None

        return {
            "external_id": f"osm_{osm_element['id']}",
            "asset_name": name,
            "asset_type": asset_type,
            "latitude": lat,
            "longitude": lon,
            "is_critical": is_critical,
            # Placeholder for capacity (OSM rarely provides this directly in a uniform way)
            "capacity": None,
            "capacity_unit": None,
            "vulnerability_level": "moderate"
        }
