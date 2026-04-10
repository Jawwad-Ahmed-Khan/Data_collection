import json
from datetime import datetime

from app.models.reference_models import ApiRegistry
from app.models.seismic_models import SeismicEvent
from app.models.weather_models import WeatherHourlyWindow
from app.models.flood_models import FloodGaugeCurrent
from app.models.breach_models import ThresholdBreachLog
from app.models.cycle_models import CollectionCycle

try:
    print("Trying to instantiate Pydantic schemas...")
    
    api = ApiRegistry(
        api_id=1,
        api_name="test_api",
        display_name="Test API",
        base_url="http://test",
        max_requests_per_minute=60,
        timeout_seconds=10.0
    )
    print("ApiRegistry OK")
    
    seismic = SeismicEvent(
        event_id="test_uuid",
        usgs_event_id="usgs123",
        magnitude=4.5,
        magnitude_class="light",
        depth_km=10.0,
        depth_class="shallow",
        latitude=30.0,
        longitude=70.0,
        earthquake_time=datetime.now(),
        first_seen_at=datetime.now(),
        last_refreshed_at=datetime.now()
    )
    print("SeismicEvent OK")
    
    print("ALL MODELS IMPORTED AND INSTANTIATED SUCCESSFULLY.")
except Exception as e:
    import sys
    print(f"ERROR: {e}")
    sys.exit(1)
