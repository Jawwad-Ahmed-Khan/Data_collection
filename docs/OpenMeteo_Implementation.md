# Open-Meteo Weather Collector Implementation

**Complete documentation for the Open-Meteo weather forecast collection system**

---

## Overview

The Open-Meteo collector monitors weather conditions across 15 Pakistan locations by polling the Open-Meteo Weather API every 15 minutes. It collects 5-day hourly and daily forecasts, computes rolling precipitation sums, sets weather flags, checks for threshold breaches, and stores data in the database.

### Key Features

- **Multi-location monitoring**: 15 Pakistan locations
- **Dual forecast types**: Hourly (120 hours) + Daily (5 days)
- **Rolling precipitation**: 24-hour and 72-hour sums
- **Weather flags**: Extreme heat, heatwave, heavy rain, storms, cold waves
- **Breach detection**: Temperature threshold checking
- **Rate limiting**: 500ms delay between location calls
- **Forecast tracking**: Day offset and horizon hours

---

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                 Open-Meteo Collector Flow                    │
└─────────────────────────────────────────────────────────────┘

1. OpenMeteoCollector (collectors/openmeteo_collector.py)
   ├─ Inherits from BaseCollector
   ├─ Filters due locations
   ├─ Collects hourly + daily for each location
   ├─ 500ms delay between locations
   └─ Manages collection cycle

2. OpenMeteoService (services/openmeteo_service.py)
   ├─ Builds query parameters (hourly/daily)
   ├─ Parses hourly forecasts (120 hours)
   ├─ Parses daily summaries (5 days)
   ├─ Computes rolling precipitation sums
   ├─ Sets weather flags
   ├─ Checks threshold breaches
   └─ UPSERTs to database

3. WeatherRepository (repositories/weather_repository.py)
   ├─ upsert_hourly() - Insert or update hourly forecast
   └─ upsert_daily() - Insert or update daily summary

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
│   Scheduler  │ Every 15 minutes
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────────────────────────────┐
│ OpenMeteoCollector.collect()                             │
├──────────────────────────────────────────────────────────┤
│ 1. Start cycle tracking (cycle_repository)              │
│ 2. Get due locations (all active for now)               │
│ 3. For each location:                                    │
│    a. Collect hourly forecast (120 hours)               │
│    b. Collect daily forecast (5 days)                   │
│    c. Process data (parse, check breaches, UPSERT)      │
│    d. Sleep 500ms (rate limit)                          │
│ 4. Complete cycle tracking with statistics              │
└──────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────┐
│ OpenMeteoService.collect_location()                     │
├──────────────────────────────────────────────────────────┤
│ 1. Build hourly query parameters                        │
│ 2. HTTP GET hourly forecast                             │
│ 3. Parse hourly response → 120 records                  │
│ 4. Build daily query parameters                         │
│ 5. HTTP GET daily forecast                              │
│ 6. Parse daily response → 5 records                     │
│ 7. Process location data                                │
└──────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────┐
│ OpenMeteoService.parse_hourly()                         │
├──────────────────────────────────────────────────────────┤
│ For each hour in forecast:                              │
│ 1. Extract 14 core variables                            │
│ 2. Convert wind direction (degrees → cardinal)          │
│ 3. Decode WMO weather code                              │
│ 4. Compute rolling sums (24h, 72h precipitation)        │
│ 5. Set weather flags (heat, rain, storm, cold)          │
│ 6. Create WeatherHourlyWindowBase object                │
└──────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────┐
│ OpenMeteoService.process_location()                     │
├──────────────────────────────────────────────────────────┤
│ For each hourly record:                                  │
│ 1. Check breach (temperature thresholds)                │
│ 2. Update record with breach info                       │
│ 3. UPSERT to weather_hourly_window table                │
│                                                          │
│ For each daily summary:                                  │
│ 1. UPSERT to weather_daily_summary table                │
└──────────────────────────────────────────────────────────┘
```

### 2. Rolling Precipitation Calculation

```
┌──────────────────────────────────────────────────────────┐
│ Rolling Precipitation Sums                               │
├──────────────────────────────────────────────────────────┤
│ For each hourly record at index i:                      │
│                                                          │
│ 24-hour sum:                                             │
│   precip_24h_mm = sum(precip_mm[i-23:i+1])              │
│   (sum of current hour + previous 23 hours)             │
│                                                          │
│ 72-hour sum:                                             │
│   precip_72h_mm = sum(precip_mm[i-71:i+1])              │
│   (sum of current hour + previous 71 hours)             │
│                                                          │
│ Example:                                                 │
│   Hour 0: precip=1mm → precip_24h=1mm, precip_72h=1mm   │
│   Hour 23: precip=1mm → precip_24h=24mm, precip_72h=24mm│
│   Hour 71: precip=1mm → precip_24h=24mm, precip_72h=72mm│
│   Hour 72: precip=1mm → precip_24h=24mm, precip_72h=72mm│
└──────────────────────────────────────────────────────────┘
```

### 3. Weather Flag Logic

```
┌──────────────────────────────────────────────────────────┐
│ Weather Flags (set per hourly record)                   │
├──────────────────────────────────────────────────────────┤
│ flag_extreme_heat:     temp_c >= 45.0                   │
│ flag_heatwave:         temp_c >= 40.0                   │
│ flag_heavy_rain:       precip_24h_mm >= 50.0            │
│ flag_very_heavy_rain:  precip_24h_mm >= 100.0           │
│ flag_storm:            wind_gusts_kmh >= 60.0           │
│ flag_severe_storm:     wind_gusts_kmh >= 90.0           │
│ flag_cold_wave:        temp_c <= 5.0                    │
└──────────────────────────────────────────────────────────┘
```

---

## Implementation Details

### File Structure

```
app/
├── collectors/
│   └── openmeteo_collector.py     # HTTP polling and cycle management
├── services/
│   └── openmeteo_service.py       # Forecast parsing and processing
├── repositories/
│   └── weather_repository.py      # Database operations
├── models/
│   └── weather_models.py          # Pydantic models
└── database/queries/
    └── weather_queries.py         # SQL queries
```

### Key Classes

#### 1. OpenMeteoCollector

**Location**: `app/collectors/openmeteo_collector.py`

**Responsibilities**:
- Filter locations due for polling
- Build Open-Meteo API query parameters
- Execute HTTP GET requests for each location
- Apply 500ms rate limit delay between locations
- Manage collection cycle tracking

**Key Methods**:
```python
def get_due_locations() -> list[PakistanLocation]:
    """Get locations that are due for polling."""
    # Currently returns all active locations
    # Future: filter by next_poll_due_at <= now()
    # Sort by poll_priority (critical first)

async def collect_location(location: PakistanLocation) -> dict:
    """Collect hourly and daily data for single location."""
    # 1. Build hourly params
    # 2. HTTP GET hourly forecast
    # 3. Build daily params
    # 4. HTTP GET daily forecast
    # 5. Parse both responses
    # 6. Process data (breach check, UPSERT)
    # Returns: location statistics

async def collect() -> dict:
    """Execute one weather collection cycle."""
    # 1. Start cycle tracking
    # 2. Get due locations
    # 3. For each location:
    #    - Collect data
    #    - Sleep 500ms
    # 4. Complete cycle tracking
    # Returns: cycle statistics
```

#### 2. OpenMeteoService

**Location**: `app/services/openmeteo_service.py`

**Responsibilities**:
- Build query parameters for hourly and daily forecasts
- Parse Open-Meteo API responses
- Compute rolling precipitation sums
- Set weather flags based on thresholds
- Convert wind direction and weather codes
- Check threshold breaches
- UPSERT forecasts to database

**Key Methods**:

```python
def build_hourly_params(latitude: float, longitude: float) -> dict:
    """Build Open-Meteo hourly query parameters."""
    # 14 core variables (simplified from 19)
    # 5-day forecast
    # Asia/Karachi timezone

def build_daily_params(latitude: float, longitude: float) -> dict:
    """Build Open-Meteo daily query parameters."""
    # 11 core variables (simplified from 14)
    # 5-day forecast
    # Asia/Karachi timezone

def parse_hourly(response: dict, location: PakistanLocation) -> list:
    """Parse hourly weather data from Open-Meteo response."""
    # Extract 120 hourly records
    # Compute rolling sums
    # Set weather flags
    # Return list of WeatherHourlyWindowBase

def parse_daily(response: dict, location: PakistanLocation) -> list:
    """Parse daily weather summaries from Open-Meteo response."""
    # Extract 5 daily records
    # Set daily flags
    # Return list of WeatherDailySummaryBase

def _compute_rolling_sums(records: list) -> None:
    """Compute rolling precipitation sums (24h, 72h)."""
    # For each record:
    #   - Sum previous 24 hours
    #   - Sum previous 72 hours

def _set_weather_flags(record: WeatherHourlyWindowBase) -> None:
    """Set weather flags based on thresholds."""
    # Check temperature, precipitation, wind
    # Set appropriate flags

def _wind_to_cardinal(degrees: int) -> str:
    """Convert wind direction degrees to cardinal direction."""
    # 0° = N, 45° = NE, 90° = E, etc.

def _decode_weather_code(code: int) -> tuple[str, str]:
    """Decode WMO weather code to condition and description."""
    # WMO code → (condition, description)
    # 0 = clear, 61 = rain, 95 = thunderstorm, etc.

async def check_breach(record: WeatherHourlyWindowBase) -> tuple:
    """Check if weather metrics cross thresholds."""
    # Check temperature thresholds
    # Create breach if detected
    # Return (has_breach, severity, metric, value)

async def process_location(hourly_records: list, daily_summaries: list) -> dict:
    """Process weather data for a location."""
    # For each hourly record:
    #   - Check breach
    #   - UPSERT to database
    # For each daily summary:
    #   - UPSERT to database
    # Return statistics
```

#### 3. WeatherRepository

**Location**: `app/repositories/weather_repository.py`

**Key Methods**:
```python
async def upsert_hourly(weather: WeatherHourlyWindowBase) -> None:
    """Insert or update an hourly weather window record."""
    # ON CONFLICT (location_id, forecast_for_datetime) DO UPDATE
    # Updates all fields on conflict

async def upsert_daily(summary: WeatherDailySummaryBase) -> None:
    """Insert or update a daily weather summary record."""
    # ON CONFLICT (location_id, summary_date) DO UPDATE
    # Updates all fields on conflict
```

---

## Data Models

### WeatherHourlyWindowBase

**Location**: `app/models/weather_models.py`

```python
class WeatherHourlyWindowBase(BaseModel):
    location_id: UUID
    location_key: str
    location_name: str
    district: str
    province: str
    latitude: float
    longitude: float
    forecast_for_datetime: datetime        # When forecast is for (PKT)
    forecast_date: date                    # Date of forecast
    day_offset: int                        # Days from today (0-4)
    
    # Core weather variables
    temp_c: float                          # Temperature (°C)
    temp_apparent_c: float                 # Feels like temperature
    temp_dewpoint_c: float | None          # Dew point
    precip_mm: float                       # Precipitation (mm)
    precip_prob_pct: int | None            # Precipitation probability (%)
    precip_24h_mm: float | None            # 24-hour rolling sum
    precip_72h_mm: float | None            # 72-hour rolling sum
    
    # Wind
    wind_speed_kmh: float | None           # Wind speed (km/h)
    wind_gusts_kmh: float | None           # Wind gusts (km/h)
    wind_direction_deg: int | None         # Wind direction (degrees)
    wind_direction_cardinal: str | None    # Wind direction (N, NE, E, etc.)
    
    # Other variables
    humidity_pct: int | None               # Relative humidity (%)
    pressure_hpa: float | None             # Surface pressure (hPa)
    visibility_m: float | None             # Visibility (meters)
    uv_index: float | None                 # UV index
    weather_code: int | None               # WMO weather code
    weather_condition: str | None          # Decoded condition
    weather_description: str | None        # Human-readable description
    is_daytime: bool = True                # Day or night
    
    # Weather flags
    flag_extreme_heat: bool = False        # >= 45°C
    flag_heatwave: bool = False            # >= 40°C
    flag_heavy_rain: bool = False          # >= 50mm in 24h
    flag_very_heavy_rain: bool = False     # >= 100mm in 24h
    flag_storm: bool = False               # Wind gusts >= 60 km/h
    flag_severe_storm: bool = False        # Wind gusts >= 90 km/h
    flag_cold_wave: bool = False           # <= 5°C
    
    # Breach tracking
    has_breach: bool = False
    breach_severity: str | None            # watch, warning, emergency, extreme
    breach_metric: str | None
    breach_observed_value: float | None
```

### WeatherDailySummaryBase

```python
class WeatherDailySummaryBase(BaseModel):
    location_id: UUID
    location_key: str
    location_name: str
    district: str
    province: str
    latitude: float
    longitude: float
    summary_date: date                     # Date of summary
    day_offset: int                        # Days from today (0-4)
    
    # Temperature
    temp_max_c: float                      # Maximum temperature
    temp_min_c: float                      # Minimum temperature
    feels_like_max_c: float | None         # Max feels like
    feels_like_min_c: float | None         # Min feels like
    
    # Precipitation
    precip_total_mm: float                 # Total precipitation
    precip_prob_max_pct: int | None        # Max precipitation probability
    
    # Wind
    wind_speed_max_kmh: float | None       # Max wind speed
    wind_gusts_max_kmh: float | None       # Max wind gusts
    
    # Other
    uv_index_max: float | None             # Max UV index
    sunrise_at: datetime | None            # Sunrise time (PKT)
    sunset_at: datetime | None             # Sunset time (PKT)
    dominant_condition: str | None         # Most common condition
    
    # Daily flags
    flag_extreme_heat_day: bool = False    # Max >= 45°C
    flag_heatwave_day: bool = False        # Max >= 40°C
    flag_heavy_rain_day: bool = False      # Total >= 50mm
    flag_storm_day: bool = False           # Gusts >= 60 km/h
    flag_cold_wave_day: bool = False       # Min <= 5°C
    
    # Worst breach of the day
    worst_breach_severity: str | None
```

### Database Schema

**Table**: `weather_hourly_window`

```sql
CREATE TABLE weather_hourly_window (
    location_id UUID NOT NULL,
    location_key TEXT NOT NULL,
    location_name TEXT NOT NULL,
    district TEXT NOT NULL,
    province TEXT NOT NULL,
    latitude NUMERIC(8,5) NOT NULL,
    longitude NUMERIC(8,5) NOT NULL,
    forecast_for_datetime TIMESTAMPTZ NOT NULL,
    forecast_date DATE NOT NULL,
    day_offset INTEGER NOT NULL,
    temp_c NUMERIC(4,1) NOT NULL,
    temp_apparent_c NUMERIC(4,1) NOT NULL,
    temp_dewpoint_c NUMERIC(4,1),
    precip_mm NUMERIC(6,2) NOT NULL,
    precip_prob_pct INTEGER,
    precip_24h_mm NUMERIC(7,2),
    precip_72h_mm NUMERIC(8,2),
    wind_speed_kmh NUMERIC(5,1),
    wind_gusts_kmh NUMERIC(5,1),
    wind_direction_deg INTEGER,
    wind_direction_cardinal TEXT,
    humidity_pct INTEGER,
    pressure_hpa NUMERIC(6,1),
    visibility_m NUMERIC(8,1),
    uv_index NUMERIC(3,1),
    weather_code INTEGER,
    weather_condition TEXT,
    weather_description TEXT,
    is_daytime BOOLEAN DEFAULT TRUE,
    flag_extreme_heat BOOLEAN DEFAULT FALSE,
    flag_heatwave BOOLEAN DEFAULT FALSE,
    flag_heavy_rain BOOLEAN DEFAULT FALSE,
    flag_very_heavy_rain BOOLEAN DEFAULT FALSE,
    flag_storm BOOLEAN DEFAULT FALSE,
    flag_severe_storm BOOLEAN DEFAULT FALSE,
    flag_cold_wave BOOLEAN DEFAULT FALSE,
    has_breach BOOLEAN DEFAULT FALSE,
    breach_severity TEXT,
    breach_metric TEXT,
    breach_observed_value NUMERIC(10,2),
    last_updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (location_id, forecast_for_datetime)
);

CREATE INDEX idx_weather_hourly_time ON weather_hourly_window(forecast_for_datetime DESC);
CREATE INDEX idx_weather_hourly_flags ON weather_hourly_window(flag_extreme_heat, flag_heatwave, flag_heavy_rain);
```

**Table**: `weather_daily_summary`

```sql
CREATE TABLE weather_daily_summary (
    location_id UUID NOT NULL,
    location_key TEXT NOT NULL,
    location_name TEXT NOT NULL,
    district TEXT NOT NULL,
    province TEXT NOT NULL,
    latitude NUMERIC(8,5) NOT NULL,
    longitude NUMERIC(8,5) NOT NULL,
    summary_date DATE NOT NULL,
    day_offset INTEGER NOT NULL,
    temp_max_c NUMERIC(4,1) NOT NULL,
    temp_min_c NUMERIC(4,1) NOT NULL,
    feels_like_max_c NUMERIC(4,1),
    feels_like_min_c NUMERIC(4,1),
    precip_total_mm NUMERIC(6,2) NOT NULL,
    precip_prob_max_pct INTEGER,
    wind_speed_max_kmh NUMERIC(5,1),
    wind_gusts_max_kmh NUMERIC(5,1),
    uv_index_max NUMERIC(3,1),
    sunrise_at TIMESTAMPTZ,
    sunset_at TIMESTAMPTZ,
    dominant_condition TEXT,
    flag_extreme_heat_day BOOLEAN DEFAULT FALSE,
    flag_heatwave_day BOOLEAN DEFAULT FALSE,
    flag_heavy_rain_day BOOLEAN DEFAULT FALSE,
    flag_storm_day BOOLEAN DEFAULT FALSE,
    flag_cold_wave_day BOOLEAN DEFAULT FALSE,
    worst_breach_severity TEXT,
    last_updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (location_id, summary_date)
);

CREATE INDEX idx_weather_daily_date ON weather_daily_summary(summary_date DESC);
```

---

## Configuration

### Environment Variables

```bash
# Open-Meteo API Configuration
OPENMETEO_BASE_URL=https://api.open-meteo.com/v1/forecast
OPENMETEO_POLL_INTERVAL_MINUTES=15
OPENMETEO_REQUEST_DELAY_MS=500
```

### Scheduler Configuration

```python
# Job 2: Weather Collection
scheduler.add_job(
    openmeteo_collector.collect,
    trigger=IntervalTrigger(minutes=15),
    id="weather_collection",
    name="Open-Meteo Weather Collection",
    max_instances=1,
    coalesce=True,
    misfire_grace_time=30,
)
```

### Query Parameters

**Hourly Forecast**:
```python
{
    "latitude": 31.5497,
    "longitude": 74.3436,
    "hourly": "temperature_2m,apparent_temperature,dew_point_2m,precipitation,precipitation_probability,wind_speed_10m,wind_gusts_10m,wind_direction_10m,relative_humidity_2m,surface_pressure,visibility,uv_index,weather_code,is_day",
    "timezone": "Asia/Karachi",
    "forecast_days": 5
}
```

**Daily Forecast**:
```python
{
    "latitude": 31.5497,
    "longitude": 74.3436,
    "daily": "temperature_2m_max,temperature_2m_min,apparent_temperature_max,apparent_temperature_min,precipitation_sum,precipitation_probability_max,wind_speed_10m_max,wind_gusts_10m_max,uv_index_max,sunrise,sunset",
    "timezone": "Asia/Karachi",
    "forecast_days": 5
}
```

---

## API Response Format

### Open-Meteo Hourly Response

```json
{
  "latitude": 31.5497,
  "longitude": 74.3436,
  "timezone": "Asia/Karachi",
  "hourly": {
    "time": [
      "2024-01-01T00:00",
      "2024-01-01T01:00",
      "..."
    ],
    "temperature_2m": [25.0, 24.5, "..."],
    "apparent_temperature": [24.0, 23.5, "..."],
    "precipitation": [0.0, 0.5, "..."],
    "wind_speed_10m": [10.0, 12.0, "..."],
    "weather_code": [0, 1, "..."]
  }
}
```

---

## Breach Detection

### Temperature Threshold Example

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
    applies_season,
    is_active
) VALUES (
    'heatwave',
    'temp_max_c',
    'punjab',
    'Lahore',
    'celsius',
    'above',
    38.0,   -- Watch: 38°C+
    40.0,   -- Warning: 40°C+
    45.0,   -- Emergency: 45°C+
    50.0,   -- Extreme: 50°C+
    'summer',
    TRUE
);
```

### Duplicate Suppression

**Temperature breaches**: 180-minute suppression window
- Prevents duplicate alerts for same location
- Allows temperature to fluctuate without spam
- New breach only if 3+ hours since last

---

## Weather Code Mapping

### WMO Weather Codes (Simplified)

```python
{
    0: ("clear", "Clear sky"),
    1: ("partly_cloudy", "Mainly clear"),
    2: ("partly_cloudy", "Partly cloudy"),
    3: ("overcast", "Overcast"),
    45: ("fog", "Fog"),
    48: ("fog", "Depositing rime fog"),
    51: ("drizzle", "Light drizzle"),
    53: ("drizzle", "Moderate drizzle"),
    55: ("drizzle", "Dense drizzle"),
    61: ("rain", "Slight rain"),
    63: ("rain", "Moderate rain"),
    65: ("heavy_rain", "Heavy rain"),
    71: ("snow", "Slight snow"),
    73: ("snow", "Moderate snow"),
    75: ("heavy_snow", "Heavy snow"),
    80: ("rain_showers", "Slight rain showers"),
    81: ("rain_showers", "Moderate rain showers"),
    82: ("rain_showers", "Violent rain showers"),
    95: ("thunderstorm", "Thunderstorm"),
    96: ("thunderstorm_with_hail", "Thunderstorm with slight hail"),
    99: ("thunderstorm_with_hail", "Thunderstorm with heavy hail"),
}
```

---

## Testing

### Unit Tests

**Location**: `tests/test_openmeteo_service.py`

**Coverage**: 25 tests covering:
- Query parameter building
- Hourly and daily data parsing
- Rolling precipitation sums (24h, 72h)
- Weather flag setting
- Wind direction conversion
- Weather code decoding
- Breach detection
- Location data processing

**Example Test**:
```python
def test_compute_rolling_sums_24h(openmeteo_service, sample_location):
    """Test 24-hour rolling precipitation sum calculation."""
    # Create 25 hourly records with 1mm precipitation each
    # First record: 1mm
    # 24th record: 24mm
    # 25th record: 24mm (rolling window)
    assert records[0].precip_24h_mm == 1.0
    assert records[23].precip_24h_mm == 24.0
    assert records[24].precip_24h_mm == 24.0
```

---

## Performance Characteristics

### Timing

- **Poll interval**: 15 minutes
- **Locations per cycle**: 15
- **Delay between locations**: 500ms
- **Total cycle time**: ~15-20 seconds
- **HTTP timeout**: 30 seconds per request

### Data Volume

- **Hourly records per location**: 120 (5 days × 24 hours)
- **Daily records per location**: 5
- **Total per cycle**: 1,800 hourly + 75 daily = 1,875 records
- **Database growth**: ~180,000 hourly + 7,500 daily per day
- **Retention**: 7 days hourly, 14 days daily

### Resource Usage

- **Memory**: ~50 MB per cycle
- **CPU**: < 5% average
- **Network**: ~50-100 KB per location
- **Database**: ~2 KB per hourly record, ~1 KB per daily

---

## Monitoring

### Cycle Tracking

```python
{
    "cycle_id": "uuid",
    "status": "completed",
    "locations_targeted": 15,
    "locations_success": 15,
    "locations_failed": 0,
    "hourly_rows": 1800,
    "daily_rows": 75,
    "breaches_detected": 2,
}
```

### Health Monitoring

```bash
GET /health/apis

{
  "apis": [
    {
      "api_name": "open_meteo",
      "is_active": true,
      "last_success_at": "2024-01-01T00:00:00+05:00",
      "consecutive_failures": 0
    }
  ]
}
```

---

## Troubleshooting

### Common Issues

**1. Rate limit exceeded**
```
Cause: Too many requests too quickly
Solution: 500ms delay enforced between locations
Check: Verify delay is applied
```

**2. Missing data for location**
```
Cause: Invalid coordinates or API error
Solution: Check location coordinates
Check: API response for errors
```

**3. Rolling sums incorrect**
```
Cause: Insufficient historical data
Solution: Normal for first 24/72 hours
Check: Wait for data accumulation
```

---

## Best Practices

1. **Monitor all 15 locations** - Ensure complete coverage
2. **Check weather flags** - Use for quick filtering
3. **Use rolling sums** - Better than single-hour precipitation
4. **Monitor breach dispatch** - Ensure alerts reach main system
5. **Archive old data** - Cleanup runs daily

---

## References

- **API Documentation**: https://open-meteo.com/en/docs
- **WMO Codes**: https://www.nodc.noaa.gov/archive/arc0021/0002199/1.1/data/0-data/HTML/WMO-CODE/WMO4677.HTM
- **Related Files**: See file structure section

---

**Last Updated**: 2024-01-01  
**Version**: 1.0.0  
**Status**: Production Ready ✅
