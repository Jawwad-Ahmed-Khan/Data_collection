# ClimaSync.ai — Secure WebSocket Implementation (Admin Only)

> **Document Type:** AI Implementation Specification  
> **Target:** Main Backend System (FastAPI)  
> **Goal:** Implement a secure WebSocket connection that **only allows Admin users** to connect and receive real-time disaster alerts, rejecting NGO users and unauthenticated requests.

---

## 1. The Challenge with WebSockets and Authentication

Unlike standard HTTP requests where you can easily pass an `Authorization: Bearer <token>` header, WebSockets initiated from a browser (via JavaScript's `new WebSocket()`) **cannot send custom headers**. 

To authenticate a WebSocket, we must pass the user's authentication token as a **Query Parameter** in the URL during the connection handshake.

Example Frontend Request:
`ws://localhost:8001/ws/alerts?token=eyJhbGciOiJIUzI1...`

---

## 2. Core Implementation Strategy

1. **Extract the Token:** The FastAPI WebSocket endpoint reads the `token` query parameter.
2. **Decode and Verify:** The backend decodes the JWT (JSON Web Token) to ensure it is valid and hasn't expired.
3. **Check User Role:** The backend checks the `role` inside the token. If `role == "admin"`, the connection is accepted. If `role == "ngo"`, the connection is rejected instantly.

---

## 3. Implementation Code

### Step A: The Connection Manager

Create the manager that holds the active Admin connections.

```python
# app/websockets/manager.py
from fastapi import WebSocket
import logging

logger = logging.getLogger(__name__)

class AdminAlertConnectionManager:
    def __init__(self):
        self.active_admin_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_admin_connections.append(websocket)
        logger.info(f"Admin connected. Total active Admins: {len(self.active_admin_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_admin_connections:
            self.active_admin_connections.remove(websocket)
            logger.info(f"Admin disconnected. Remaining: {len(self.active_admin_connections)}")

    async def broadcast_alert(self, alert_data: dict):
        """Broadcasts only to verified Admin connections."""
        dead_connections = []
        for connection in self.active_admin_connections:
            try:
                await connection.send_json({
                    "event": "NEW_DISASTER_ALERT",
                    "data": alert_data
                })
            except Exception as e:
                logger.error(f"Failed to send to an Admin, marking dead. Error: {e}")
                dead_connections.append(connection)
        
        for dead in dead_connections:
            self.disconnect(dead)

admin_ws_manager = AdminAlertConnectionManager()
```

---

### Step B: The Authentication Dependency

Create a function to validate the JWT token passed in the query parameter and strictly check for the "admin" role.

*(Note: Adjust `SECRET_KEY` and `ALGORITHM` to match your actual JWT auth setup in the Main Backend).*

```python
# app/core/ws_auth.py
from fastapi import WebSocket, WebSocketException, status, Query
from jose import JWTError, jwt

SECRET_KEY = "your-super-secret-jwt-key" # Load from environment in production
ALGORITHM = "HS256"

async def verify_admin_ws_token(websocket: WebSocket, token: str = Query(None)):
    """
    Dependency to verify the WebSocket token.
    Must return the decoded payload if valid AND user is an Admin.
    Closes the connection immediately if invalid or unauthorized.
    """
    if token is None:
        # HTTP 403 equivalent for WebSockets
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Missing token")

    try:
        # Decode the JWT token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_role = payload.get("role")
        
        # STRICT ROLE CHECK: ONLY ADMIN
        if user_role != "admin":
            logger.warning(f"Unauthorized WS attempt by role: {user_role}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Admin access required")
            
        return payload # Success!

    except JWTError:
        logger.warning("Invalid JWT token provided for WebSocket")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
```

---

### Step C: The Protected WebSocket Endpoint

Now, combine the Manager and the Auth Dependency in your routing file.

```python
# app/main.py (or your routing file)
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from app.websockets.manager import admin_ws_manager
from app.core.ws_auth import verify_admin_ws_token

app = FastAPI()

@app.websocket("/ws/alerts")
async def websocket_alerts_endpoint(
    websocket: WebSocket, 
    # The Depends() automatically runs our verification before accepting the connection
    admin_data: dict = Depends(verify_admin_ws_token) 
):
    """
    Secure endpoint. Only execution reaches here if `verify_admin_ws_token` passed.
    """
    await admin_ws_manager.connect(websocket)
    
    # You can log who connected if your token has their ID/Email
    # admin_email = admin_data.get("sub")
    
    try:
        while True:
            # Keep the connection alive
            await websocket.receive_text()
            
    except WebSocketDisconnect:
        admin_ws_manager.disconnect(websocket)
```

---

### Step D: Triggering the Broadcast

When the `/alerts/incoming` POST request hits from the Data Collection Service, you broadcast using the new `admin_ws_manager`.

```python
# app/api/routes/alerts.py
from fastapi import APIRouter, status
from app.models.schemas.alert_schemas import IncomingBreachPayload
from app.websockets.manager import admin_ws_manager

router = APIRouter()

@router.post("/alerts/incoming", status_code=status.HTTP_201_CREATED)
async def receive_incoming_alert(payload: IncomingBreachPayload):
    
    alert_json = payload.model_dump(mode='json')
    
    # This will now ONLY send data to users who passed the Admin verification
    await admin_ws_manager.broadcast_alert(alert_json)
    
    return {"status": "success", "alert_id": payload.breach_id}
```

---

## 4. Frontend Integration Note

When the Frontend (React, Vue, etc.) connects to this endpoint, the developer must append the Admin's JWT token to the URL string.

**Correct Frontend Code:**
```javascript
// 1. Get the admin's login token from LocalStorage or Context
const adminToken = localStorage.getItem("access_token");

// 2. Append it to the URL query string
const socket = new WebSocket(`ws://localhost:8001/ws/alerts?token=${adminToken}`);

socket.onmessage = function(event) {
    const data = JSON.parse(event.data);
    console.log("Secure Admin Alert Received:", data);
};
```

If an NGO user attempts this, their token will decode with `role: "ngo"`, and the FastAPI backend will immediately drop the connection with `WS_1008_POLICY_VIOLATION` (Status 1008), preventing them from receiving any data.