# ClimaSync.ai — Main Backend Alert Integration Guide

> **Document Type:** AI Implementation Specification  
> **Target:** Main Backend System (FastAPI)  
> **Goal:** Implement the `/alerts/incoming` endpoint to receive data from the Data Collection Service and broadcast it to the Frontend via WebSockets.

---

## 1. Context and Architecture

The **Data Collection Service** (a separate microservice) continuously monitors USGS, Open-Meteo, and Google Flood Hub. When a disaster threshold is breached, it automatically sends an HTTP POST request to the **Main Backend System**.

Your task is to implement the receiving end in the Main Backend. 

The architecture flow is:
`Data Collection Service (Sender) -> HTTP POST -> Main Backend (Receiver) -> Save to DB -> WebSocket -> Frontend UI`

---

## 2. The Data Model (Examples of Incoming JSON)

The Data Collection Service uses a unified JSON structure, but specific ID fields change depending on the disaster source. Here is exactly what the POST JSON bodies look like when they hit the Main Backend (`http://localhost:8001/alerts/incoming`). These examples must guide your database schema and Pydantic validation.

### Example 1: Earthquake Data (from USGS)
For an earthquake, the system sends the `usgs_event_id` (mapped to `seismic_event_id`) so your main backend can track USGS revisions if the magnitude is updated later. Notice that `is_forecast` is always `false` because earthquakes cannot be predicted.

```json
{
    "breach_id": "a1b2c3d4-e5f6-7890-1234-56789abcdef0",
    "source_api": "usgs",
    "disaster_kind": "earthquake",
    "metric_name": "magnitude",
    "location_name": "Muzaffarabad",
    "district": "muzaffarabad",
    "province": "azad_kashmir",
    "latitude": 34.3596,
    "longitude": 73.4715,
    "observed_value": 6.2,
    "threshold_value": 6.0,
    "breach_severity": "emergency",
    "unit": "richter",
    "observation_time": "2025-07-15T10:15:00+05:00",
    "is_forecast": false,
    "forecast_horizon_h": null,
    "detected_at": "2025-07-15T10:18:00+05:00",
    "seismic_event_id": "us2024test001"
}
```

### Example 2: Flood Data (from Google Flood Hub)
For a flood, the system includes the `gauge_id` (the specific river monitoring station). Floods can be current readings OR forecasts. The example below shows a **Forecast Breach** (predicting a flood 36 hours in the future).

```json
{
    "breach_id": "b2c3d4e5-f6a7-8901-2345-6789abcdef01",
    "source_api": "google_flood_hub",
    "disaster_kind": "flood",
    "metric_name": "gauge_pct_of_danger",
    "location_name": "Sukkur",
    "district": "sukkur",
    "province": "sindh",
    "latitude": 27.7135,
    "longitude": 68.8524,
    "observed_value": 105.3,
    "threshold_value": 100.0,
    "breach_severity": "emergency",
    "unit": "percent",
    "observation_time": "2025-07-17T02:30:00+05:00",
    "is_forecast": true,
    "forecast_horizon_h": 36,
    "detected_at": "2025-07-15T14:30:00+05:00",
    "gauge_id": "google-gauge-sukkur-001"
}
```

### Example 3: Weather Data (from Open-Meteo)
For weather (Heatwaves, Heavy Rain, Cyclones, etc.), the system includes the `weather_location_id` (the specific city/district being monitored). Like floods, weather alerts are almost always **Forecasts**. This example shows a predictive heatwave alert.

```json
{
    "breach_id": "c3d4e5f6-a7b8-9012-3456-789abcdef012",
    "source_api": "open_meteo",
    "disaster_kind": "heatwave",
    "metric_name": "temp_max_c",
    "location_name": "Larkana",
    "district": "larkana",
    "province": "sindh",
    "latitude": 27.5589,
    "longitude": 68.2120,
    "observed_value": 49.5,
    "threshold_value": 49.0,
    "breach_severity": "emergency",
    "unit": "celsius",
    "observation_time": "2025-07-18T14:00:00+05:00",
    "is_forecast": true,
    "forecast_horizon_h": 72,
    "detected_at": "2025-07-15T14:00:00+05:00",
    "weather_location_id": "larkana_27.5589_68.2120"
}
```

---

## 3. Pydantic Model Implementation

Create the following Pydantic model in the Main Backend (e.g., in `app/models/schemas/alert_schemas.py`) to strictly validate the incoming JSON examples above.

```python
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class IncomingBreachPayload(BaseModel):
    # Core Identifiers
    breach_id: str = Field(..., description="Unique UUID from the Collection Database")
    source_api: str = Field(..., description="'usgs', 'open_meteo', or 'google_flood_hub'")
    disaster_kind: str = Field(..., description="'earthquake', 'flood', 'heatwave', 'heavy_rain', etc.")
    
    # Location Data
    location_name: Optional[str] = Field(None, description="Human readable city/district name")
    district: Optional[str] = Field(None, description="Pakistan district")
    province: Optional[str] = Field(None, description="Pakistan province enum string")
    latitude: float = Field(..., description="Latitude coordinate")
    longitude: float = Field(..., description="Longitude coordinate")
    
    # Metrics
    metric_name: str = Field(..., description="The type of reading (e.g., 'magnitude', 'temp_max_c')")
    observed_value: float = Field(..., description="The actual reading or forecasted value")
    threshold_value: float = Field(..., description="The limit that was crossed")
    unit: str = Field(..., description="Unit of measurement ('richter', 'celsius', 'mm', 'percent')")
    breach_severity: str = Field(..., description="'watch', 'warning', 'emergency', or 'extreme'")
    
    # Timing
    observation_time: datetime = Field(..., description="When the event happens (or is forecasted to happen)")
    detected_at: datetime = Field(..., description="When the collection service detected the breach")
    is_forecast: bool = Field(False, description="True if this is a future prediction")
    forecast_horizon_h: Optional[int] = Field(None, description="Hours in the future (if is_forecast is true)")
    
    # Specific API Foreign Keys (At least one will be present depending on source_api)
    seismic_event_id: Optional[str] = Field(None, description="USGS specific event ID")
    weather_location_id: Optional[str] = Field(None, description="Open-Meteo internal location ID")
    gauge_id: Optional[str] = Field(None, description="Google Flood Hub specific river gauge ID")
```

---

## 4. The FastAPI Endpoint Implementation

Create the endpoint that catches the POST request. 

**Requirements for the endpoint:**
1. Method must be `POST`.
2. Path must be exactly `/alerts/incoming`.
3. It should accept an optional `X-API-Key` header (to be verified later when security is enabled).
4. It must return a `200` or `201` status code with `{"status": "success", "alert_id": "<the_breach_id>"}` so the Collection Service knows it was received successfully.

**Implementation (e.g., in `app/api/routes/alerts.py`):**

```python
from fastapi import APIRouter, Header, HTTPException, Depends, status
from app.models.schemas.alert_schemas import IncomingBreachPayload
# Note: You will need to import your actual database session and websocket manager
# from app.db.session import get_db
# from app.websockets.manager import ws_manager

router = APIRouter()

# Placeholder for future security implementation
EXPECTED_API_KEY = "your_secret_key_here" # In production, load from os.getenv("MAIN_SYSTEM_API_KEY")

@router.post("/alerts/incoming", status_code=status.HTTP_201_CREATED)
async def receive_incoming_alert(
    payload: IncomingBreachPayload,
    x_api_key: str = Header(None)
):
    """
    Receives disaster breach payloads from the Data Collection Service.
    """
    # 1. Security Check (Optional right now, but good practice)
    # If the key is provided but wrong, reject it. If not provided, let it pass for now.
    if x_api_key and x_api_key != EXPECTED_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key")

    try:
        # 2. Save to Main Database
        # AI Task: Implement the SQLAlchemy/AsyncPG logic here to save the payload
        # to the main operational database (e.g., into an `alerts` table).
        # db.save_alert(payload)

        # 3. Broadcast to Frontend via WebSockets
        # AI Task: Call your websocket manager to push this payload to all connected clients.
        # await ws_manager.broadcast_alert(payload.model_dump(mode='json'))
        
        # 4. (Future) Trigger Verification Agent
        # agent_service.trigger_verification(payload.breach_id)

        # 5. Return success to Data Collection Service
        return {
            "status": "success", 
            "alert_id": payload.breach_id,
            "message": "Alert received and broadcasted"
        }

    except Exception as e:
        # Return a 500 error so the Collection Service knows to retry later
        raise HTTPException(status_code=500, detail=str(e))
```

---

## 5. WebSocket Implementation (Backend to Frontend)

To make the map flash red instantly when a disaster hits, you need WebSockets. The frontend will connect to `ws://localhost:8001/ws/alerts`.

**Implementation (e.g., in `app/websockets/manager.py`):**

```python
from fastapi import WebSocket, WebSocketDisconnect
import json
import logging

logger = logging.getLogger(__name__)

class AlertConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Frontend client connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("Frontend client disconnected.")

    async def broadcast_alert(self, alert_data: dict):
        """
        Sends the JSON payload to all connected frontend clients.
        """
        dead_connections = []
        for connection in self.active_connections:
            try:
                # Send the incoming payload exactly as received
                await connection.send_json({
                    "event": "NEW_DISASTER_ALERT",
                    "data": alert_data
                })
            except Exception as e:
                logger.error(f"Failed to send to a websocket client: {e}")
                dead_connections.append(connection)
        
        # Cleanup dead connections
        for dead in dead_connections:
            self.disconnect(dead)

ws_manager = AlertConnectionManager()
```

**Add the WebSocket Route (e.g., in `app/main.py`):**

```python
from fastapi import WebSocket, WebSocketDisconnect
from app.websockets.manager import ws_manager

@app.websocket("/ws/alerts")
async def websocket_alerts_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # The backend just listens to keep the connection alive.
            # The frontend doesn't need to send messages here, it only receives.
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
```

---

## 6. Summary of AI Developer Tasks

If you are an AI implementing this spec in the Main Backend, complete the following checklist:

1. **Create Pydantic Schema**: Create `IncomingBreachPayload` to exactly match the JSON structures provided in Section 2.
2. **Create REST Endpoint**: Create `POST /alerts/incoming`. Ensure it parses the Pydantic schema and returns a `200` or `201` with `{"status": "success", "alert_id": "<uuid>"}`.
3. **Implement WebSocket Manager**: Create the class to track connected clients and broadcast JSON data.
4. **Create WebSocket Route**: Expose `ws://<domain>/ws/alerts` for the frontend to connect to.
5. **Connect the Flow**: Inside `POST /alerts/incoming`, after validating the data, call `await ws_manager.broadcast_alert(payload.model_dump(mode='json'))`.
6. **Database Persistence**: (Optional but highly recommended) Save the incoming payload to an `alerts` table in the main PostgreSQL database before broadcasting.