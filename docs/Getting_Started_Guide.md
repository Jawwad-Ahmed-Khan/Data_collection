# ClimaSync Collection Service - Getting Started Guide

**Complete guide to running, testing, and monitoring the ClimaSync Data Collection Service**

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [Running the Service](#running-the-service)
5. [Swagger UI Documentation](#swagger-ui-documentation)
6. [Testing API Endpoints](#testing-api-endpoints)
7. [Monitoring Collection Cycles](#monitoring-collection-cycles)
8. [Manual Collection Triggers](#manual-collection-triggers)
9. [Troubleshooting](#troubleshooting)
10. [Production Deployment](#production-deployment)

---

## Prerequisites

### Required Software

- **Python**: 3.12 or higher
- **uv**: Python package manager (recommended)
- **PostgreSQL**: 14+ (Supabase recommended)
- **Git**: For cloning the repository

### Required Accounts

- **Supabase Account**: For PostgreSQL database
- **Google Cloud Account**: For Flood Hub API access

### System Requirements

- **OS**: Linux, macOS, or Windows (WSL recommended)
- **RAM**: Minimum 2GB
- **Disk**: Minimum 1GB free space
- **Network**: Internet connection for API calls

---

## Installation

### Step 1: Clone the Repository

```bash
git clone https://github.com/your-org/climasync-collection.git
cd climasync-collection
```

### Step 2: Install uv (if not already installed)

**Linux/macOS**:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows**:
```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Step 3: Create Virtual Environment

```bash
uv venv
source .venv/bin/activate  # Linux/macOS
# or
.venv\Scripts\activate  # Windows
```

### Step 4: Install Dependencies

```bash
uv pip install -e .
```

### Step 5: Verify Installation

```bash
python -c "import fastapi; import asyncpg; import httpx; print('All dependencies installed!')"
```

---

## Configuration

### Step 1: Create Environment File

Copy the example environment file:

```bash
cp .env.example .env
```

### Step 2: Configure Database (Supabase)

Edit `.env` and add your Supabase credentials:

```bash
# Database Configuration
COLLECTION_DB_HOST=db.your-project.supabase.co
COLLECTION_DB_PORT=5432
COLLECTION_DB_NAME=postgres
COLLECTION_DB_USER=postgres
COLLECTION_DB_PASSWORD=your-supabase-password
COLLECTION_DB_POOL_MIN=2
COLLECTION_DB_POOL_MAX=10
```

**How to get Supabase credentials**:
1. Go to https://supabase.com/dashboard
2. Select your project
3. Go to Settings → Database
4. Copy connection details

### Step 3: Configure Main System Connection

```bash
# Main System Configuration
MAIN_SYSTEM_BASE_URL=https://your-main-system.com/api
MAIN_SYSTEM_API_KEY=your-api-key-here
```

### Step 4: Configure Google Flood Hub API

```bash
# Google Flood Hub Configuration
GOOGLE_FLOOD_HUB_BASE_URL=https://floodhub.googleapis.com/v1
GOOGLE_FLOOD_HUB_API_KEY=your-google-cloud-api-key
```

**How to get Google Cloud API key**:
1. Go to https://console.cloud.google.com/
2. Create a new project or select existing
3. Enable Flood Hub API
4. Go to APIs & Services → Credentials
5. Create API Key

### Step 5: Configure Application Settings

```bash
# Application Configuration
APP_PORT=8000
APP_ENV=development
LOG_LEVEL=INFO
SERVICE_NAME=climasync-collection

# API Configuration (defaults are fine)
USGS_BASE_URL=https://earthquake.usgs.gov/fdsnws/event/1/query
USGS_MIN_MAGNITUDE=2.5
USGS_LOOKBACK_HOURS=6
USGS_POLL_INTERVAL_SECONDS=60

OPENMETEO_BASE_URL=https://api.open-meteo.com/v1/forecast
OPENMETEO_POLL_INTERVAL_MINUTES=15
OPENMETEO_REQUEST_DELAY_MS=500

# Collection Intervals
FLOOD_CURRENT_INTERVAL_MINUTES=30
FLOOD_FORECAST_INTERVAL_HOURS=6
BREACH_DISPATCH_INTERVAL_SECONDS=30
THRESHOLD_RELOAD_INTERVAL_HOURS=1
CLEANUP_HOUR_PKT=0
CLEANUP_MINUTE_PKT=5

# Dispatch Settings
MAX_DISPATCH_ATTEMPTS=5
DISPATCH_BATCH_SIZE=10
```

### Step 6: Verify Configuration

```bash
python -c "from app.core.config import get_settings; s = get_settings(); print(f'Config loaded: {s.service_name}')"
```

---

## Running the Service

### Development Mode

**Option 1: Using uv**
```bash
uv run python -m app.main
```

**Option 2: Using Python directly**
```bash
python -m app.main
```

**Option 3: Using uvicorn directly**
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Production Mode

```bash
# Set production environment
export APP_ENV=production
export LOG_LEVEL=WARNING

# Run with uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Expected Startup Output

```
======================================================================
ClimaSync Collection Service — Starting Up
======================================================================
✓ Step 1/7: Configuration loaded (service=climasync-collection, env=development)
✓ Step 2/7: Logger initialized (level=INFO)
✓ Step 3/7: Database connected (pool_size=2-10)
✓ Step 4/7: Reference data loaded:
  - 15 Pakistan locations
  - 21 disaster thresholds
  - 3 API configurations
  - 10 flood gauges
✓ Step 5/7: Components initialized:
  - HTTP client (timeout=30s)
  - Repositories (seismic, breach, cycle, reference, weather, flood)
  - Services (breach, USGS, Open-Meteo, Flood Hub, dispatch)
  - Collectors (USGS, Open-Meteo, Flood Hub)
✓ Job 1/7: USGS collection (every 60s)
✓ Job 2/7: Weather collection (every 15min)
✓ Job 3/7: Flood current readings (every 30min)
✓ Job 4/7: Flood forecasts (every 6h)
✓ Job 5/7: Breach dispatch (every 30s)
✓ Job 6/7: Threshold reload (every 1h)
✓ Job 7/7: Daily cleanup (at 00:05 PKT)
✓ Step 6/7: Scheduler started with 7 jobs:
✓ Step 7/7: Startup complete!
======================================================================
ClimaSync Collection Service is READY
  - API: http://0.0.0.0:8000
  - Health: http://0.0.0.0:8000/health
  - Status: http://0.0.0.0:8000/status/cycles
======================================================================
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

---

## Swagger UI Documentation

### Accessing Swagger UI

Once the service is running, open your browser and navigate to:

```
http://localhost:8000/docs
```

### Swagger UI Features

The Swagger UI provides:
- **Interactive API documentation**
- **Try it out** functionality for each endpoint
- **Request/response schemas**
- **Authentication testing**
- **Real-time API testing**

### Swagger UI Interface

```
┌─────────────────────────────────────────────────────────────┐
│  ClimaSync Collection Service                               │
│  Version: 0.1.0                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  📁 default                                                 │
│    GET  /                    Root endpoint                  │
│    POST /trigger/usgs        Manual USGS trigger            │
│                                                             │
│  📁 health                                                  │
│    GET  /health              Health check                   │
│    GET  /health/apis         API health status             │
│                                                             │
│  📁 status                                                  │
│    GET  /status/cycles       Collection cycles             │
│    GET  /status/breaches     Breach statistics             │
│    GET  /status/locations    Location polling status       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Testing API Endpoints

### 1. Root Endpoint

**Purpose**: Verify service is running

**Endpoint**: `GET /`

**Swagger UI Steps**:
1. Click on `GET /` endpoint
2. Click "Try it out"
3. Click "Execute"

**Expected Response**:
```json
{
  "service": "ClimaSync Collection Service",
  "version": "0.1.0",
  "status": "operational",
  "endpoints": {
    "health": "/health",
    "api_health": "/health/apis",
    "cycles": "/status/cycles",
    "breaches": "/status/breaches",
    "locations": "/status/locations"
  }
}
```

**Using curl**:
```bash
curl http://localhost:8000/
```

---

### 2. Health Check Endpoint

**Purpose**: Check service health and database connection

**Endpoint**: `GET /health`

**Swagger UI Steps**:
1. Click on `GET /health` endpoint
2. Click "Try it out"
3. Add `X-API-Key` header (click "Add string item" under Headers)
   - Key: `X-API-Key`
   - Value: Your API key from `.env` (MAIN_SYSTEM_API_KEY)
4. Click "Execute"

**Expected Response**:
```json
{
  "status": "healthy",
  "database_connected": true,
  "uptime_seconds": 3600,
  "timestamp_pkt": "2024-01-01T12:00:00+05:00"
}
```

**Using curl**:
```bash
curl -H "X-API-Key: your-api-key" http://localhost:8000/health
```

**Troubleshooting**:
- **403 Forbidden**: API key is missing or incorrect
- **database_connected: false**: Database connection failed, check `.env` credentials

---

### 3. API Health Status

**Purpose**: Check health of external APIs (USGS, Open-Meteo, Flood Hub)

**Endpoint**: `GET /health/apis`

**Swagger UI Steps**:
1. Click on `GET /health/apis` endpoint
2. Click "Try it out"
3. Add `X-API-Key` header
4. Click "Execute"

**Expected Response**:
```json
{
  "apis": [
    {
      "api_name": "usgs",
      "display_name": "USGS Earthquake API",
      "is_active": true,
      "last_success_at": "2024-01-01T12:00:00+05:00",
      "consecutive_failures": 0,
      "is_in_backoff": false,
      "backoff_remaining_seconds": 0
    },
    {
      "api_name": "open_meteo",
      "display_name": "Open-Meteo Weather API",
      "is_active": true,
      "last_success_at": "2024-01-01T11:45:00+05:00",
      "consecutive_failures": 0,
      "is_in_backoff": false,
      "backoff_remaining_seconds": 0
    },
    {
      "api_name": "google_flood_hub",
      "display_name": "Google Flood Hub API",
      "is_active": true,
      "last_success_at": "2024-01-01T11:30:00+05:00",
      "consecutive_failures": 0,
      "is_in_backoff": false,
      "backoff_remaining_seconds": 0
    }
  ]
}
```

**Using curl**:
```bash
curl -H "X-API-Key: your-api-key" http://localhost:8000/health/apis
```

**What to Check**:
- ✅ `is_active: true` - API is enabled
- ✅ `consecutive_failures: 0` - No recent failures
- ✅ `is_in_backoff: false` - Not rate limited
- ⚠️ `consecutive_failures > 5` - API having issues
- ⚠️ `is_in_backoff: true` - Rate limited, check `backoff_remaining_seconds`

---

### 4. Collection Cycles Status

**Purpose**: View recent collection cycles for all APIs

**Endpoint**: `GET /status/cycles`

**Swagger UI Steps**:
1. Click on `GET /status/cycles` endpoint
2. Click "Try it out"
3. Add `X-API-Key` header
4. Click "Execute"

**Expected Response**:
```json
{
  "cycles": [
    {
      "api_name": "usgs",
      "cycle_id": "550e8400-e29b-41d4-a716-446655440000",
      "status": "completed",
      "locations_targeted": 1,
      "locations_success": 1,
      "locations_failed": 0,
      "rows_upserted": 5,
      "rows_inserted": 3,
      "breaches_triggered": 1,
      "rate_limit_hits": 0,
      "started_at": "2024-01-01T12:00:00+05:00",
      "completed_at": "2024-01-01T12:00:05+05:00"
    },
    {
      "api_name": "open_meteo",
      "cycle_id": "550e8400-e29b-41d4-a716-446655440001",
      "status": "completed",
      "locations_targeted": 15,
      "locations_success": 15,
      "locations_failed": 0,
      "rows_upserted": 1875,
      "breaches_triggered": 2,
      "started_at": "2024-01-01T11:45:00+05:00",
      "completed_at": "2024-01-01T11:45:20+05:00"
    },
    {
      "api_name": "google_flood_hub",
      "cycle_id": "550e8400-e29b-41d4-a716-446655440002",
      "status": "completed",
      "locations_targeted": 10,
      "locations_success": 10,
      "locations_failed": 0,
      "rows_upserted": 10,
      "breaches_triggered": 0,
      "started_at": "2024-01-01T11:30:00+05:00",
      "completed_at": "2024-01-01T11:30:15+05:00"
    }
  ]
}
```

**Using curl**:
```bash
curl -H "X-API-Key: your-api-key" http://localhost:8000/status/cycles
```

**Cycle Status Values**:
- `completed` - All locations successful
- `partial` - Some locations failed
- `failed` - All locations failed
- `skipped` - No locations to poll

**What to Check**:
- ✅ `status: "completed"` - Cycle successful
- ✅ `locations_success > 0` - Data collected
- ✅ `rows_upserted > 0` - Data stored in database
- ⚠️ `status: "partial"` - Some failures, check logs
- ❌ `status: "failed"` - Complete failure, check API health

---

### 5. Breach Statistics

**Purpose**: View breach counts and dispatch status

**Endpoint**: `GET /status/breaches`

**Swagger UI Steps**:
1. Click on `GET /status/breaches` endpoint
2. Click "Try it out"
3. Add `X-API-Key` header
4. Click "Execute"

**Expected Response**:
```json
{
  "breaches": {
    "pending": 5,
    "dispatched": 120,
    "dispatch_failed": 2,
    "ignored": 0
  },
  "last_breach_at": "2024-01-01T12:00:00+05:00",
  "last_dispatch_at": "2024-01-01T12:00:30+05:00"
}
```

**Using curl**:
```bash
curl -H "X-API-Key: your-api-key" http://localhost:8000/status/breaches
```

**What to Check**:
- ✅ `pending: 0-10` - Normal queue
- ✅ `dispatched > 0` - Breaches being sent to main system
- ⚠️ `pending > 50` - Dispatch backlog, check main system
- ⚠️ `dispatch_failed > 10` - Dispatch issues, check main system connectivity

---

### 6. Location Polling Status

**Purpose**: View polling status for all monitored locations

**Endpoint**: `GET /status/locations`

**Swagger UI Steps**:
1. Click on `GET /status/locations` endpoint
2. Click "Try it out"
3. Add `X-API-Key` header
4. Click "Execute"

**Expected Response**:
```json
{
  "locations": [
    {
      "location_name": "Lahore",
      "district": "Lahore",
      "province": "punjab",
      "last_polled_at": "2024-01-01T11:45:00+05:00",
      "next_poll_due_at": "2024-01-01T12:00:00+05:00",
      "consecutive_failures": 0,
      "is_active": true
    },
    {
      "location_name": "Karachi",
      "district": "Karachi",
      "province": "sindh",
      "last_polled_at": "2024-01-01T11:45:00+05:00",
      "next_poll_due_at": "2024-01-01T12:00:00+05:00",
      "consecutive_failures": 0,
      "is_active": true
    }
  ]
}
```

**Using curl**:
```bash
curl -H "X-API-Key: your-api-key" http://localhost:8000/status/locations
```

**What to Check**:
- ✅ `consecutive_failures: 0` - Location polling healthy
- ✅ `is_active: true` - Location enabled
- ⚠️ `consecutive_failures > 3` - Location having issues
- ⚠️ `last_polled_at` is old - Polling may be stuck

---

### 7. Manual USGS Collection Trigger

**Purpose**: Manually trigger USGS earthquake collection (for testing)

**Endpoint**: `POST /trigger/usgs`

**Swagger UI Steps**:
1. Click on `POST /trigger/usgs` endpoint
2. Click "Try it out"
3. Add `X-API-Key` header
4. Click "Execute"

**Expected Response**:
```json
{
  "cycle_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "locations_targeted": 1,
  "locations_success": 1,
  "locations_failed": 0,
  "events_processed": 5,
  "events_upserted": 5,
  "breaches_detected": 1,
  "error": null
}
```

**Using curl**:
```bash
curl -X POST -H "X-API-Key: your-api-key" http://localhost:8000/trigger/usgs
```

**What to Check**:
- ✅ `status: "completed"` - Collection successful
- ✅ `events_processed > 0` - Earthquakes found
- ✅ `breaches_detected >= 0` - Threshold checking working
- ⚠️ `events_processed: 0` - No earthquakes (normal if no seismic activity)
- ❌ `status: "failed"` - Collection failed, check error message

---

## Monitoring Collection Cycles

### Real-Time Monitoring

**Watch logs in real-time**:
```bash
# Follow logs
tail -f logs/climasync-collection.log

# Filter for specific collector
tail -f logs/climasync-collection.log | grep "USGS"
tail -f logs/climasync-collection.log | grep "Weather"
tail -f logs/climasync-collection.log | grep "Flood"
```

### Database Monitoring

**Check recent seismic events**:
```sql
SELECT 
    usgs_event_id,
    magnitude,
    magnitude_class,
    earthquake_time,
    resolved_location_name,
    has_breach
FROM seismic_events
ORDER BY earthquake_time DESC
LIMIT 10;
```

**Check recent weather data**:
```sql
SELECT 
    location_name,
    forecast_for_datetime,
    temp_c,
    precip_mm,
    flag_extreme_heat,
    flag_heavy_rain,
    has_breach
FROM weather_hourly_window
WHERE location_name = 'Lahore'
ORDER BY forecast_for_datetime DESC
LIMIT 24;
```

**Check flood gauge status**:
```sql
SELECT 
    gauge_name,
    river_name,
    current_level_m,
    pct_of_danger,
    river_trend,
    flood_status,
    has_breach
FROM flood_gauge_current
ORDER BY pct_of_danger DESC;
```

**Check breach log**:
```sql
SELECT 
    source_api,
    disaster_kind,
    metric_name,
    location_name,
    observed_value,
    breach_severity,
    dispatch_status,
    detected_at
FROM threshold_breach_log
ORDER BY detected_at DESC
LIMIT 20;
```

**Check collection cycles**:
```sql
SELECT 
    api_name,
    status,
    locations_success,
    locations_failed,
    rows_upserted,
    breaches_triggered,
    started_at,
    completed_at
FROM collection_cycles
ORDER BY started_at DESC
LIMIT 20;
```

---

## Manual Collection Triggers

### Trigger Individual Collectors

While the service runs automatically, you can manually trigger collections for testing:

**USGS Collection**:
```bash
curl -X POST -H "X-API-Key: your-api-key" http://localhost:8000/trigger/usgs
```

**Note**: Manual triggers for Weather and Flood Hub are not exposed by default. To add them, you can create similar endpoints in `main.py`.

### Python Script for Testing

Create `test_collection.py`:

```python
import asyncio
import httpx

async def test_usgs():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/trigger/usgs",
            headers={"X-API-Key": "your-api-key"},
            timeout=60.0,
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")

if __name__ == "__main__":
    asyncio.run(test_usgs())
```

Run:
```bash
python test_collection.py
```

---

## Troubleshooting

### Service Won't Start

**Problem**: Service fails to start

**Check**:
1. Database connection:
   ```bash
   psql -h db.your-project.supabase.co -U postgres -d postgres
   ```
2. Environment variables:
   ```bash
   python -c "from app.core.config import get_settings; get_settings()"
   ```
3. Port availability:
   ```bash
   lsof -i :8000  # Linux/macOS
   netstat -ano | findstr :8000  # Windows
   ```

**Solution**:
- Fix database credentials in `.env`
- Ensure all required env vars are set
- Use different port: `uvicorn app.main:app --port 8001`

---

### API Returns 403 Forbidden

**Problem**: All API calls return 403

**Cause**: Missing or incorrect API key

**Solution**:
1. Check `.env` file has `MAIN_SYSTEM_API_KEY`
2. Use correct header: `X-API-Key: your-api-key`
3. In Swagger UI, click "Authorize" button and enter API key

---

### No Data Being Collected

**Problem**: Cycles run but no data appears

**Check**:
1. API health: `GET /health/apis`
2. Recent cycles: `GET /status/cycles`
3. Database tables:
   ```sql
   SELECT COUNT(*) FROM seismic_events;
   SELECT COUNT(*) FROM weather_hourly_window;
   SELECT COUNT(*) FROM flood_gauge_current;
   ```

**Solution**:
- Check API credentials (especially Google Flood Hub)
- Verify network connectivity
- Check logs for errors
- Ensure reference data is loaded (locations, thresholds)

---

### Breaches Not Being Dispatched

**Problem**: Breaches detected but not dispatched

**Check**:
1. Breach status: `GET /status/breaches`
2. Main system connectivity:
   ```bash
   curl -H "X-API-Key: your-api-key" https://your-main-system.com/api/health
   ```
3. Dispatch logs:
   ```bash
   tail -f logs/climasync-collection.log | grep "Dispatch"
   ```

**Solution**:
- Verify `MAIN_SYSTEM_BASE_URL` is correct
- Verify `MAIN_SYSTEM_API_KEY` is valid
- Check main system is accepting requests
- Check `dispatch_attempt_count` in database (max 5 attempts)

---

### High Memory Usage

**Problem**: Service using too much memory

**Check**:
```bash
ps aux | grep python
```

**Solution**:
- Reduce database pool size: `COLLECTION_DB_POOL_MAX=5`
- Reduce forecast days (requires code change)
- Monitor for memory leaks in logs
- Restart service periodically

---

## Production Deployment

### Using Docker (Recommended)

**Create Dockerfile**:
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install uv
RUN pip install uv

# Copy project files
COPY . .

# Install dependencies
RUN uv pip install --system -e .

# Expose port
EXPOSE 8000

# Run service
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Build and run**:
```bash
docker build -t climasync-collection .
docker run -p 8000:8000 --env-file .env climasync-collection
```

### Using systemd (Linux)

**Create service file** `/etc/systemd/system/climasync-collection.service`:
```ini
[Unit]
Description=ClimaSync Collection Service
After=network.target

[Service]
Type=simple
User=climasync
WorkingDirectory=/opt/climasync-collection
Environment="PATH=/opt/climasync-collection/.venv/bin"
EnvironmentFile=/opt/climasync-collection/.env
ExecStart=/opt/climasync-collection/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Enable and start**:
```bash
sudo systemctl enable climasync-collection
sudo systemctl start climasync-collection
sudo systemctl status climasync-collection
```

### Using PM2 (Node.js Process Manager)

```bash
# Install PM2
npm install -g pm2

# Start service
pm2 start "uvicorn app.main:app --host 0.0.0.0 --port 8000" --name climasync-collection

# Save configuration
pm2 save

# Setup startup script
pm2 startup
```

### Nginx Reverse Proxy

**Create nginx config** `/etc/nginx/sites-available/climasync-collection`:
```nginx
server {
    listen 80;
    server_name collection.climasync.ai;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Enable and reload**:
```bash
sudo ln -s /etc/nginx/sites-available/climasync-collection /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## Quick Reference

### Essential Commands

```bash
# Start service
uv run python -m app.main

# Check health
curl http://localhost:8000/health

# View logs
tail -f logs/climasync-collection.log

# Trigger USGS collection
curl -X POST -H "X-API-Key: your-api-key" http://localhost:8000/trigger/usgs

# Check cycles
curl -H "X-API-Key: your-api-key" http://localhost:8000/status/cycles

# Check breaches
curl -H "X-API-Key: your-api-key" http://localhost:8000/status/breaches
```

### Important URLs

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json
- **Health Check**: http://localhost:8000/health

### Default Intervals

- **USGS**: Every 60 seconds
- **Weather**: Every 15 minutes
- **Flood Current**: Every 30 minutes
- **Flood Forecasts**: Every 6 hours
- **Breach Dispatch**: Every 30 seconds
- **Threshold Reload**: Every 1 hour
- **Daily Cleanup**: 00:05 PKT

---

## Support

### Documentation

- **USGS Implementation**: `docs/USGS_Implementation.md`
- **OpenMeteo Implementation**: `docs/OpenMeteo_Implementation.md`
- **FloodHub Implementation**: `docs/FloodHub_Implementation.md`
- **Project Overview**: `Project_overview.md`
- **Task List**: `Task_List.md`

### Logs

- **Application logs**: `logs/climasync-collection.log`
- **Error logs**: Check stderr output
- **Database logs**: Supabase dashboard

### Getting Help

1. Check logs for error messages
2. Review Swagger UI for API documentation
3. Check database for data issues
4. Review configuration in `.env`
5. Consult implementation documentation

---

**Last Updated**: 2024-01-01  
**Version**: 1.0.0  
**Status**: Production Ready ✅
