# USGS Earthquake Collector Implementation

**Complete documentation for the USGS earthquake data collection system**

---

## Overview

The USGS (United States Geological Survey) collector monitors earthquake activity in and around Pakistan by polling the USGS Earthquake API every 60 seconds. It detects seismic events, resolves their nearest Pakistan location, checks for threshold breaches, and stores data in the database.

### Key Features

- **Real-time monitoring**: Polls USGS API every 60 seconds
- **Geographic filtering**: Pakistan bounding box (23°N-38°N, 60°E-78°E)
- **Magnitude filtering**: Minimum M2.5 earthquakes
- **6-hour lookback**: Catches event revisions and updates
- **Location resolution**: Haversine distance to nearest Pakistan location
- **Breach detection**: Automatic threshold checking
- **Duplicate handling**: UPSERT prevents duplicate events

---

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                    USGS Collector Flow                       │
└─────────────────────────────────────────────────────────────┘

1. USGSCollector (collectors/usgs_collector.py)
   ├─ Inherits from BaseCollector
   ├─ Builds query parameters
   ├─ Executes HTTP GET request
   └─ Manages collection cycle

2. USGSService (services/usgs_service.py)
   ├─ Parses GeoJSON response
   ├─ Converts timestamps to PKT
   ├─ Classifies magnitude and depth
   ├─ Resolves nearest location
   ├─ Checks threshold breaches
   └─ UPSERTs to database

3. SeismicRepository (repositories/seismic_repository.py)
   ├─ upsert_event() - Insert or update event
   ├─ get_recent_events() - Fetch recent events
   └─ delete_old_events() - Cleanup expired data

4. BreachService (services/breach_service.py)
   ├─ find_applicable_threshold() - Lookup threshold
   ├─ check_breach() - Compare value vs threshold
   └─ create_breach() - Log breach alert
```

---

## Data Flow

### 1. Collection Cycle

```
┌──────────────┐
│   Scheduler  │ Every 60 seconds
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────────────────────────────┐
│ USGSCollector.collect()                                  │
├──────────────────────────────────────────────────────────┤
│ 1. Start cycle tracking (cycle_repository)              │
│ 2. Build query parameters:                              │
│    - format=geojson                                      │
│    - minmagnitude=2.5                                    │
│    - starttime=(now - 6 hours)                           │
│    - endtime=now                                         │
│    - minlatitude=23.0, maxlatitude=38.0                  │
│    - minlongitude=60.0, maxlongitude=78.0                │
│ 3. HTTP GET to USGS API                                  │
│ 4. Pass response to USGSService                          │
│ 5. Complete cycle tracking with statistics              │
└──────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────┐
│ USGSService.parse_usgs_response()                       │
├──────────────────────────────────────────────────────────┤
│ For each feature in GeoJSON:                            │
│ 1. Extract event ID from feature.id                     │
│ 2. Extract magnitude, depth, coordinates                │
│ 3. Convert unix milliseconds → PKT datetime             │
│ 4. Classify magnitude (micro/minor/light/moderate...)   │
│ 5. Classify depth (shallow/intermediate/deep)           │
│ 6. Find nearest Pakistan location (Haversine)           │
│ 7. Create SeismicEventBase object                       │
└──────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────┐
│ USGSService.process_events()                            │
├──────────────────────────────────────────────────────────┤
│ For each event:                                          │
│ 1. Check breach (BreachService)                         │
│ 2. Update event with breach info                        │
│ 3. UPSERT to seismic_events table                       │
└──────────────────────────────────────────────────────────┘
```

### 2. Breach Detection Flow

```
┌──────────────────────────────────────────────────────────┐
│ BreachService.check_breach(event)                       │
├──────────────────────────────────────────────────────────┤
│ 1. Find applicable threshold:                           │
│    - metric_name = "magnitude"                           │
│    - disaster_kind = "earthquake"                        │
│    - Priority: district > province > national           │
│                                                          │
│ 2. Compare magnitude vs threshold levels:               │
│    - watch_threshold (e.g., 4.0)                         │
│    - warning_threshold (e.g., 5.0)                       │
│    - emergency_threshold (e.g., 6.0)                     │
│    - extreme_threshold (e.g., 7.0)                       │
│                                                          │
│ 3. If breach detected:                                   │
│    - Create breach log entry                             │
│    - Set dispatch_status = 'pending'                     │
│    - Return severity level                               │
└──────────────────────────────────────────────────────────┘
```

---

## Implementation Details

### File Structure

```
app/
├── collectors/
│   └── usgs_collector.py          # HTTP polling and cycle management
├── services/
│   └── usgs_service.py            # GeoJSON parsing and processing
├── repositories/
│   └── seismic_repository.py      # Database operations
├── models/
│   └── seismic_models.py          # Pydantic models
└── database/queries/
    └── seismic_queries.py         # SQL queries
```

### Key Classes

#### 1. USGSCollector

**Location**: `app/collectors/usgs_collector.py`

**Responsibilities**:
- Build USGS API query parameters
- Execute HTTP GET requests with retry logic
- Manage collection cycle tracking
- Handle rate limiting and backoff

**Key Methods**:
```python
async def collect() -> dict:
    """Execute one USGS collection cycle."""
    # 1. Start cycle tracking
    # 2. Build query params
    # 3. HTTP GET to USGS API
    # 4. Parse and process response
    # 5. Complete cycle tracking
    # Returns: cycle statistics
```

**Query Parameters**:
```python
{
    "format": "geojson",
    "minmagnitude": 2.5,
    "starttime": "2024-01-01T00:00:00",  # now - 6 hours
    "endtime": "2024-01-01T06:00:00",    # now
    "minlatitude": 23.0,
    "maxlatitude": 38.0,
    "minlongitude": 60.0,
    "maxlongitude": 78.0,
}
```

#### 2. USGSService

**Location**: `app/services/usgs_service.py`

**Responsibilities**:
- Parse USGS GeoJSON responses
- Convert timestamps to PKT timezone
- Classify magnitude and depth
- Resolve nearest Pakistan location
- Check threshold breaches
- UPSERT events to database

**Key Methods**:

```python
def parse_usgs_response(geojson: dict) -> list[SeismicEventBase]:
    """Parse USGS GeoJSON into SeismicEventBase objects."""
    # Extracts features array
    # Parses each feature
    # Returns list of events

def _parse_feature(feature: dict) -> SeismicEventBase | None:
    """Parse single GeoJSON feature."""
    # Extract event ID, magnitude, depth, coordinates
    # Convert timestamps
    # Classify magnitude and depth
    # Resolve nearest location
    # Return SeismicEventBase

def _convert_usgs_time(unix_ms: int) -> datetime:
    """Convert USGS unix milliseconds to PKT datetime."""
    # USGS uses unix milliseconds
    # Convert to datetime with PKT timezone

def _classify_magnitude(magnitude: float) -> str:
    """Classify magnitude into categories."""
    # < 3.0: micro
    # 3.0-3.9: minor
    # 4.0-4.9: light
    # 5.0-5.9: moderate
    # 6.0-6.9: strong
    # 7.0-7.9: major
    # >= 8.0: great

def _classify_depth(depth_km: float) -> str:
    """Classify depth into categories."""
    # < 70 km: shallow
    # 70-300 km: intermediate
    # > 300 km: deep

def _find_nearest_location(lat: float, lon: float) -> tuple:
    """Find nearest Pakistan location using Haversine distance."""
    # Calculates distance to all locations
    # Returns nearest location and distance

async def check_breach(event: SeismicEventBase) -> tuple[bool, str | None]:
    """Check if event crosses magnitude threshold."""
    # Find applicable threshold
    # Compare magnitude vs threshold levels
    # Create breach if detected
    # Return (has_breach, severity)

async def process_events(events: list) -> dict:
    """Process all events: check breaches and UPSERT."""
    # For each event:
    #   - Check breach
    #   - UPSERT to database
    # Return statistics
```

#### 3. SeismicRepository

**Location**: `app/repositories/seismic_repository.py`

**Key Methods**:
```python
async def upsert_event(event: SeismicEventBase) -> str:
    """Insert or update seismic event."""
    # ON CONFLICT (usgs_event_id) DO UPDATE
    # Returns event_id

async def get_recent_events(hours: int) -> list[SeismicEvent]:
    """Fetch recent events within time window."""
    # Used for analysis and reporting

async def delete_old_events(days: int) -> int:
    """Delete events older than specified days."""
    # Cleanup job (runs daily at 00:05 PKT)
```

---

## Data Models

### SeismicEventBase

**Location**: `app/models/seismic_models.py`

```python
class SeismicEventBase(BaseModel):
    usgs_event_id: str                    # Unique USGS identifier
    magnitude: float                      # Richter scale magnitude
    magnitude_type: str | None            # mb, ml, mw, etc.
    magnitude_class: str                  # micro, minor, light, moderate, strong, major, great
    depth_km: float                       # Depth in kilometers
    depth_class: str                      # shallow, intermediate, deep
    latitude: float                       # Event latitude
    longitude: float                      # Event longitude
    earthquake_time: datetime             # When earthquake occurred (PKT)
    usgs_place: str | None                # USGS place description
    resolved_location_name: str | None    # Nearest Pakistan location
    resolved_district: str | None         # District name
    resolved_province: str | None         # Province name
    distance_from_location_km: float | None  # Distance to nearest location
    felt_reports: int | None              # Number of "Did You Feel It?" reports
    cdi: float | None                     # Community Decimal Intensity
    mmi: float | None                     # Modified Mercalli Intensity
    usgs_alert_level: str | None          # green, yellow, orange, red
    tsunami_flag: bool = False            # Tsunami warning flag
    data_quality: str = "automatic"       # automatic, reviewed, deleted
    has_breach: bool = False              # Threshold breach detected
    breach_severity: str | None           # watch, warning, emergency, extreme
```

### Database Schema

**Table**: `seismic_events`

```sql
CREATE TABLE seismic_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    usgs_event_id TEXT UNIQUE NOT NULL,
    magnitude NUMERIC(3,1) NOT NULL,
    magnitude_type TEXT,
    magnitude_class TEXT,
    depth_km NUMERIC(6,2) NOT NULL,
    depth_class TEXT,
    latitude NUMERIC(8,5) NOT NULL,
    longitude NUMERIC(8,5) NOT NULL,
    coordinates GEOGRAPHY(POINT, 4326),
    earthquake_time TIMESTAMPTZ NOT NULL,
    usgs_place TEXT,
    resolved_location_name TEXT,
    resolved_district TEXT,
    resolved_province TEXT,
    distance_from_location_km NUMERIC(6,2),
    felt_reports INTEGER,
    cdi NUMERIC(3,1),
    mmi NUMERIC(3,1),
    usgs_alert_level TEXT,
    tsunami_flag BOOLEAN DEFAULT FALSE,
    data_quality TEXT DEFAULT 'automatic',
    has_breach BOOLEAN DEFAULT FALSE,
    breach_severity TEXT,
    last_updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_seismic_events_time ON seismic_events(earthquake_time DESC);
CREATE INDEX idx_seismic_events_magnitude ON seismic_events(magnitude DESC);
CREATE INDEX idx_seismic_events_location ON seismic_events USING GIST(coordinates);
```

---

## Configuration

### Environment Variables

```bash
# USGS API Configuration
USGS_BASE_URL=https://earthquake.usgs.gov/fdsnws/event/1/query
USGS_MIN_MAGNITUDE=2.5
USGS_LOOKBACK_HOURS=6
USGS_POLL_INTERVAL_SECONDS=60

# Pakistan Geographic Bounds
PAKISTAN_MIN_LAT=23.0
PAKISTAN_MAX_LAT=38.0
PAKISTAN_MIN_LON=60.0
PAKISTAN_MAX_LON=78.0
```

### Scheduler Configuration

```python
# Job 1: USGS Collection
scheduler.add_job(
    usgs_collector.collect,
    trigger=IntervalTrigger(seconds=60),
    id="usgs_collection",
    name="USGS Earthquake Collection",
    max_instances=1,
    coalesce=True,
    misfire_grace_time=30,
)
```

---

## API Response Format

### USGS GeoJSON Response

```json
{
  "type": "FeatureCollection",
  "metadata": {
    "generated": 1704067200000,
    "url": "https://earthquake.usgs.gov/fdsnws/event/1/query",
    "title": "USGS Earthquakes",
    "status": 200,
    "count": 2
  },
  "features": [
    {
      "type": "Feature",
      "properties": {
        "mag": 4.5,
        "place": "15 km NE of Lahore, Pakistan",
        "time": 1704067200000,
        "updated": 1704067200000,
        "tz": null,
        "url": "https://earthquake.usgs.gov/earthquakes/eventpage/us7000test1",
        "felt": 150,
        "cdi": 5.2,
        "mmi": 4.8,
        "alert": "green",
        "status": "reviewed",
        "tsunami": 0,
        "magType": "mb",
        "type": "earthquake"
      },
      "geometry": {
        "type": "Point",
        "coordinates": [74.5, 31.7, 25.0]
      },
      "id": "us7000test1"
    }
  ]
}
```

---

## Breach Detection

### Threshold Configuration

**Example threshold in database**:

```sql
INSERT INTO disaster_thresholds (
    disaster_kind,
    metric_name,
    province,
    district,
    unit,
    breach_direction,
    watch_threshold,
    warning_threshold,
    emergency_threshold,
    extreme_threshold,
    is_active
) VALUES (
    'earthquake',
    'magnitude',
    NULL,  -- National threshold
    NULL,
    'richter',
    'above',
    4.0,   -- Watch: M4.0+
    5.0,   -- Warning: M5.0+
    6.0,   -- Emergency: M6.0+
    7.0,   -- Extreme: M7.0+
    TRUE
);
```

### Breach Logic

```python
# 1. Find applicable threshold
threshold = breach_service.find_applicable_threshold(
    metric_name="magnitude",
    disaster_kind="earthquake",
    province=event.resolved_province,
    district=event.resolved_district,
)

# 2. Check if magnitude crosses threshold
severity = breach_service.check_breach(
    value=event.magnitude,
    threshold=threshold,
)

# 3. If breach detected, create breach log
if severity:
    await breach_service.create_breach(
        source_api="usgs",
        disaster_kind="earthquake",
        metric_name="magnitude",
        observed_value=event.magnitude,
        threshold=threshold,
        severity=severity,
        observation_time=event.earthquake_time,
        location_name=event.resolved_location_name,
        district=event.resolved_district,
        province=event.resolved_province,
        latitude=event.latitude,
        longitude=event.longitude,
        seismic_event_id=event_id,
    )
```

### Duplicate Suppression

**Earthquakes have NO suppression window** (0 minutes) because:
- Each earthquake is a unique event
- USGS event IDs are unique
- UPSERT on `usgs_event_id` prevents database duplicates
- Revisions update existing records

---

## Error Handling

### Retry Logic (from BaseCollector)

```python
# Tenacity retry configuration
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=1, max=30),
    retry=retry_if_exception_type((
        httpx.TimeoutException,
        httpx.ConnectError,
    )) | retry_if_exception(lambda e: isinstance(e, httpx.HTTPStatusError) and e.response.status_code >= 500),
)
async def get(url: str, params: dict) -> httpx.Response:
    """HTTP GET with retry logic."""
    # 3 attempts with exponential backoff
    # Retries on timeout, connection error, 5xx
    # Does NOT retry on 429 (rate limit)
```

### Rate Limit Handling

```python
# If HTTP 429 received:
if response.status_code == 429:
    retry_after = int(response.headers.get("Retry-After", 60))
    await reference_repo.update_api_backoff(
        api_name="usgs",
        backoff_seconds=retry_after,
    )
    # Subsequent requests check backoff_until before proceeding
```

### Error Isolation

```python
# Each job wrapped in try/except
try:
    result = await usgs_collector.collect()
    logger.info("USGS collection completed: %s", result)
except Exception as e:
    logger.error("USGS collection failed: %s", str(e), exc_info=True)
    # Error logged, other jobs continue
```

---

## Monitoring

### Cycle Tracking

Every collection cycle is tracked in `collection_cycles` table:

```python
{
    "cycle_id": "uuid",
    "api_id": "uuid",
    "status": "completed",  # completed, partial, failed, skipped
    "locations_targeted": 1,
    "locations_success": 1,
    "locations_failed": 0,
    "rows_upserted": 5,
    "rows_inserted": 3,
    "breaches_triggered": 1,
    "rate_limit_hits": 0,
    "started_at": "2024-01-01T00:00:00+05:00",
    "completed_at": "2024-01-01T00:00:05+05:00",
}
```

### Health Monitoring

```bash
# Check API health
GET /health/apis

Response:
{
  "apis": [
    {
      "api_name": "usgs",
      "is_active": true,
      "last_success_at": "2024-01-01T00:00:00+05:00",
      "consecutive_failures": 0,
      "is_in_backoff": false,
      "backoff_remaining_seconds": 0
    }
  ]
}
```

### Cycle History

```bash
# Check recent cycles
GET /status/cycles

Response:
{
  "cycles": [
    {
      "api_name": "usgs",
      "cycle_id": "uuid",
      "status": "completed",
      "locations_success": 1,
      "rows_upserted": 5,
      "breaches_triggered": 1,
      "started_at": "2024-01-01T00:00:00+05:00"
    }
  ]
}
```

---

## Testing

### Unit Tests

**Location**: `tests/test_usgs_service.py`

**Coverage**: 24 tests covering:
- GeoJSON parsing and field extraction
- Unix milliseconds to PKT datetime conversion
- Magnitude and depth classification
- Haversine distance calculation
- Nearest location resolution
- Breach detection and creation
- Event processing workflow

**Example Test**:
```python
def test_parse_usgs_response_success(usgs_service, sample_usgs_geojson):
    """Test successful parsing of USGS GeoJSON response."""
    events = usgs_service.parse_usgs_response(sample_usgs_geojson)
    
    assert len(events) == 2
    assert events[0].usgs_event_id == "us7000test1"
    assert events[0].magnitude == 4.5
    assert events[0].magnitude_class == "light"
    assert events[0].depth_class == "shallow"
```

### Integration Testing

```bash
# Manual trigger endpoint (for testing)
POST /trigger/usgs
Headers: X-API-Key: your-api-key

Response:
{
  "cycle_id": "uuid",
  "status": "completed",
  "locations_targeted": 1,
  "locations_success": 1,
  "events_processed": 5,
  "breaches_detected": 1
}
```

---

## Performance Characteristics

### Timing

- **Poll interval**: 60 seconds
- **HTTP timeout**: 30 seconds
- **Retry attempts**: 3 (with exponential backoff)
- **Average response time**: 1-3 seconds
- **Processing time**: < 1 second for typical response

### Data Volume

- **Typical events per cycle**: 0-10 events
- **Peak events per cycle**: 20-50 events (after major earthquake)
- **Database growth**: ~100-500 events per day
- **Retention**: 30 days (cleanup job deletes older)

### Resource Usage

- **Memory**: ~10 MB per cycle
- **CPU**: Minimal (< 1% average)
- **Network**: ~5-50 KB per request
- **Database**: ~1-5 KB per event

---

## Troubleshooting

### Common Issues

**1. No events collected**
```
Cause: No earthquakes in Pakistan region
Solution: Normal behavior, wait for seismic activity
Check: Verify USGS API is accessible
```

**2. HTTP 429 Rate Limit**
```
Cause: Too many requests to USGS API
Solution: Automatic backoff applied
Check: /health/apis endpoint for backoff status
```

**3. Connection timeout**
```
Cause: USGS API slow or unreachable
Solution: Automatic retry (3 attempts)
Check: Network connectivity, USGS API status
```

**4. Breach not detected**
```
Cause: Magnitude below threshold
Solution: Verify threshold configuration in database
Check: disaster_thresholds table
```

### Debug Logging

```python
# Enable debug logging
LOG_LEVEL=DEBUG

# Logs show:
# - Query parameters
# - HTTP request/response
# - Parsed events
# - Breach checks
# - Database operations
```

---

## Best Practices

### 1. Threshold Configuration

- Set national thresholds first (province=NULL, district=NULL)
- Add province-specific thresholds for high-risk areas
- Add district-specific thresholds for critical locations
- Test thresholds with historical data

### 2. Monitoring

- Monitor `/health/apis` for API health
- Monitor `/status/cycles` for collection success rate
- Set up alerts for consecutive failures (> 5)
- Monitor breach dispatch success rate

### 3. Database Maintenance

- Run cleanup job daily (00:05 PKT)
- Monitor table size growth
- Index on `earthquake_time` for fast queries
- Archive old data if needed

### 4. Error Handling

- Let retry logic handle transient failures
- Monitor backoff periods
- Alert on persistent failures (> 1 hour)
- Check USGS API status page during outages

---

## References

### USGS API Documentation

- **API Endpoint**: https://earthquake.usgs.gov/fdsnws/event/1/
- **Documentation**: https://earthquake.usgs.gov/fdsnws/event/1/
- **GeoJSON Format**: https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php
- **Status Page**: https://earthquake.usgs.gov/monitoring/operations/

### Related Files

- `app/collectors/usgs_collector.py` - Collector implementation
- `app/services/usgs_service.py` - Service implementation
- `app/repositories/seismic_repository.py` - Repository implementation
- `app/models/seismic_models.py` - Data models
- `tests/test_usgs_service.py` - Unit tests
- `tests/test_usgs_collector.py` - Collector tests

---

**Last Updated**: 2024-01-01  
**Version**: 1.0.0  
**Status**: Production Ready ✅
