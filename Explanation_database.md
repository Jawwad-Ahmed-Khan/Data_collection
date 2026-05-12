# ClimaSync.ai — Complete Database Documentation

### Data Collection Database — Technical Reference Document

---

> **Document Purpose:** This document explains every table, every column, every design decision in the ClimaSync Data Collection Database. After reading this document you will understand not just what each table stores but why it exists, what problem it solves, and how it connects to the rest of the system.

---

# SECTION 1: DATABASE OVERVIEW

## 1.1 What This Database Is

This is the **Data Collection Database** for ClimaSync.ai. It is a completely separate database from the main ClimaSync operational database. Its only responsibility is to collect raw disaster-related data from three external APIs, process it, detect threshold breaches, and hand off alerts to the main system.

Think of this database as the **eyes and ears** of ClimaSync. It watches Pakistan continuously. The main database is the **brain** that decides what to do when danger is detected.

## 1.2 What This Database Is Not

This database does not store NGO information. It does not store tasks. It does not store user accounts. It does not store social media posts. All of that lives in the main ClimaSync operational database. This database has one job and does it well.

## 1.3 The Three External Data Sources

```
┌─────────────────────────────────────────────────────────┐
│  SOURCE 1: USGS Earthquake API                          │
│  What it provides: Real-time earthquake events          │
│  Coverage: Pakistan geographic bounding box             │
│  Update frequency: Every 5 minutes                      │
│  Data type: Event-based (each earthquake = one record)  │
├─────────────────────────────────────────────────────────┤
│  SOURCE 2: Open-Meteo Weather API                       │
│  What it provides: 5-day weather forecast per location  │
│  Coverage: 270 curated coordinate points in Pakistan    │
│  Update frequency: Every 3-6 hours per location         │
│  Data type: Time-series (hourly + daily forecasts)      │
├─────────────────────────────────────────────────────────┤
│  SOURCE 3: Google Flood Hub API                         │
│  What it provides: River gauge readings + flood forecast│
│  Coverage: ~150 active river gauges in Pakistan         │
│  Update frequency: Hourly readings, 6-hourly forecasts  │
│  Data type: Current state + probabilistic forecast      │
└─────────────────────────────────────────────────────────┝
```

## 1.4 Rolling 5-Day Window Philosophy

This database does not accumulate data forever. It maintains a **rolling 5-day window** — today plus the next 4 days. When tomorrow arrives, yesterday's data is deleted and day 5 is added. This keeps the database small, fast, and focused on what matters for disaster management — the present situation and the near future.

```
┌──────────────────────────────────────────────────────────┐
│  ROLLING WINDOW EXAMPLE                                  │
│                                                          │
│  Today is 15 July 2025                                   │
│                                                          │
│  Day 0 → 15 July (Today — current conditions)           │
│  Day 1 → 16 July (Tomorrow)                             │
│  Day 2 → 17 July                                        │
│  Day 3 → 18 July                                        │
│  Day 4 → 19 July (4 days ahead)                         │
│                                                          │
│  On 16 July, 15 July data is deleted.                   │
│  20 July data is added.                                  │
│  Window always contains exactly 5 days.                  │
└──────────────────────────────────────────────────────────┘
```

## 1.5 Database Size Reality

Because of the rolling window design, this database has a fixed maximum size that never grows beyond approximately 52,500 rows total. This fits comfortably in Supabase free tier and ensures all queries are consistently fast regardless of how long the system has been running.

```
┌──────────────────────────────────────────────┐
│  TABLE                    MAX ROWS           │
│  ─────────────────────    ────────           │
│  weather_hourly_window    32,400             │
│  flood_gauge_forecasts    18,000             │
│  weather_daily_summaries   1,350             │
│  flood_gauge_current         150             │
│  seismic_events               75             │
│  threshold_breach_log        500 (approx)   │
│  Reference tables          ~800             │
│  Operational tables          ~50 active      │
│  ─────────────────────    ────────           │
│  TOTAL MAXIMUM            ~52,500            │
└──────────────────────────────────────────────┘
```

---

# SECTION 2: DATABASE CONFIGURATION

## 2.1 Timezone Setting

- **Timezone:** Asia/Karachi (Pakistan Standard Time, UTC+5)
- **Why:** All disaster events, all timestamps, all date calculations operate in Pakistan local time. A disaster at 11:30 PM PKT must be recorded as 11:30 PM PKT not 6:30 PM UTC which would place it on the wrong date for daily calculations.
- **How stored internally:** PostgreSQL stores TIMESTAMPTZ values as UTC internally always. The timezone setting controls display and input interpretation only. Your data is never corrupted by timezone settings.

## 2.2 Extensions Used

- **pgcrypto:** Enables gen_random_uuid() for generating UUID primary keys
- **postgis:** Enables GEOGRAPHY data type for storing coordinates and performing spatial distance calculations
- **citext:** Case-insensitive text type used for email fields

---

# SECTION 3: ENUM TYPES

## What Are Enums and Why Use Them

An enum is a fixed list of allowed values for a column. Instead of storing the string "healthy" or "HEALTHY" or "Healthy" in an api health column and allowing any spelling variation, you define an enum with exactly the values that are valid. PostgreSQL enforces this at the database level. No invalid value can ever be inserted. This eliminates an entire category of data quality bugs.

---

## 3.1 api_source_name

**Purpose:** Identifies which external API produced a piece of data.

**Values and meaning:**
- `usgs` — United States Geological Survey earthquake feed
- `open_meteo` — Open-Meteo weather forecast API
- `google_flood_hub` — Google Flood Hub river gauge API

**Used in tables:** api_registry, collection_cycles, threshold_breach_log

---

## 3.2 api_health_state

**Purpose:** Tracks the current operational health of each external API.

**Values and meaning:**
- `healthy` — API responding normally, all calls succeeding
- `degraded` — API responding but with elevated errors or slow responses
- `rate_limited` — API returned HTTP 429, system is in backoff mode
- `down` — API not responding, 3 or more consecutive failures
- `unknown` — Initial state before first API call is made

**Used in tables:** api_registry

---

## 3.3 cycle_status

**Purpose:** Tracks the execution state of a data collection cycle.

**Values and meaning:**
- `running` — Cycle is currently executing, polling locations
- `completed` — All locations polled successfully
- `partial` — Some locations succeeded, some failed
- `failed` — Cycle failed entirely, no data collected
- `skipped` — Cycle was due but skipped (API in backoff, system busy)

**Used in tables:** collection_cycles

---

## 3.4 poll_outcome

**Purpose:** Records the result of a single API call to a single location.

**Values and meaning:**
- `success` — API call returned valid data, data was stored
- `failed` — API call returned an error response
- `rate_limited` — API returned HTTP 429 Too Many Requests
- `timeout` — API did not respond within the timeout window
- `invalid_response` — API responded but data was malformed or unexpected
- `skipped` — Location was skipped intentionally (low priority, API in backoff)

**Used in tables:** pakistan_locations (last_poll_outcome column)

---

## 3.5 pk_province

**Purpose:** Controlled list of Pakistan's administrative provinces and territories. Ensures consistent province naming across all tables.

**Values and meaning:**
- `punjab` — Punjab Province
- `sindh` — Sindh Province
- `khyber_pakhtunkhwa` — KPK Province
- `balochistan` — Balochistan Province
- `gilgit_baltistan` — Gilgit-Baltistan Territory
- `azad_kashmir` — Azad Jammu and Kashmir
- `islamabad_capital_territory` — ICT (Federal Capital)

**Why this matters:** Without this enum, different parts of the system might store "KPK", "Khyber Pakhtunkhwa", "NWFP" for the same province. This makes geographic queries impossible to write reliably.

**Used in tables:** pakistan_locations, pakistan_infrastructure, flood_gauge_registry, flood_gauge_current, flood_gauge_forecasts, weather_hourly_window, weather_daily_summaries, seismic_events, threshold_breach_log

---

## 3.6 location_tier

**Purpose:** Classifies monitoring locations by their strategic importance for polling priority decisions.

**Values and meaning:**
- `tier_1_provincial_capital` — Karachi, Lahore, Islamabad, Quetta, Peshawar — highest priority always
- `tier_2_district_headquarters` — All 160 district capitals — medium-high priority
- `tier_3_disaster_zone` — Historically disaster-prone areas not covered by tiers 1 and 2
- `tier_3_river_basin` — Points along major river systems (Indus, Jhelum, Chenab, Ravi, Sutlej)
- `tier_3_coastal` — Coastal areas near Karachi and Makran coast
- `tier_3_mountain` — Mountain passes and high altitude areas
- `tier_3_border` — Border region monitoring points

**Used in tables:** pakistan_locations

---

## 3.7 poll_priority

**Purpose:** Controls how frequently and urgently the polling scheduler processes a location.

**Values and meaning:**
- `critical` — Poll as frequently as possible, never skip (provincial capitals during active disaster)
- `high` — Poll every 30-60 minutes (river basin points during monsoon, flood gauges always)
- `medium` — Poll every 3-6 hours (district headquarters in normal conditions)
- `low` — Poll every 6-12 hours (remote areas with historically low disaster frequency)

**Used in tables:** pakistan_locations, flood_gauge_registry

---

## 3.8 asset_type

**Purpose:** Classifies infrastructure assets for risk impact assessment.

**Values and meaning:**
- `hospital` — Full hospital with emergency and inpatient care
- `basic_health_unit` — BHU or rural health center
- `school` — Primary, secondary, or higher secondary school
- `bridge` — Road or railway bridge over water
- `dam` — Major dam structure
- `barrage` — River barrage for irrigation
- `power_station` — Electricity generation facility
- `water_treatment` — Water treatment or pumping station
- `airport` — Civil or military airport
- `flood_shelter` — Dedicated flood emergency shelter
- `evacuation_center` — Designated emergency evacuation point

**Used in tables:** pakistan_infrastructure

---

## 3.9 vulnerability_level

**Purpose:** Standardized rating of how vulnerable a location or asset is to disaster impact.

**Values and meaning:**
- `very_low` — Modern construction, good infrastructure, low exposure
- `low` — Adequate construction, reasonable infrastructure
- `moderate` — Average conditions, some risk factors present
- `high` — Poor construction quality, inadequate infrastructure
- `very_high` — Very poor conditions, high exposure, limited evacuation routes
- `critical` — Extreme risk, often informal settlements or highly exposed areas

**Used in tables:** pakistan_locations, pakistan_infrastructure

---

## 3.10 risk_zone

**Purpose:** Geographic risk zone classification for different disaster types.

**Values and meaning:**
- `zone_1_low` — Minimal historical disaster frequency or impact
- `zone_2_moderate` — Occasional events, moderate impact
- `zone_3_high` — Regular events, significant impact (most of Punjab for floods)
- `zone_4_very_high` — Frequent events, severe impact (Sindh flood plains)
- `zone_5_critical` — Extreme risk, highest historical disaster frequency (Indus delta, Chaman fault zone)

**Used in tables:** pakistan_locations

---

## 3.11 disaster_kind

**Purpose:** Classifies the type of disaster event being tracked or threshold being defined.

**Values and meaning:**
- `earthquake` — Seismic ground shaking event
- `flood` — River overflow or inundation event
- `flash_flood` — Rapid onset flooding from heavy rain, no river overflow
- `heatwave` — Sustained extreme high temperature period
- `cyclone` — Tropical cyclone or severe storm system
- `heavy_rain` — Extreme precipitation event without flooding
- `drought` — Prolonged rainfall deficiency
- `landslide` — Ground movement, often triggered by rain or earthquake
- `dust_storm` — Severe dust or sand storm
- `cold_wave` — Sustained extreme low temperature period

**Used in tables:** disaster_thresholds, threshold_breach_log

---

## 3.12 weather_condition

**Purpose:** Human-readable weather condition decoded from the raw WMO weather code returned by Open-Meteo.

**Values and meaning:**
- `clear` — WMO code 0, no clouds
- `partly_cloudy` — WMO codes 1-2, partial cloud cover
- `overcast` — WMO code 3, full cloud cover
- `fog` — WMO codes 45, 48, visibility severely reduced
- `drizzle` — WMO codes 51-55, light continuous rain
- `rain` — WMO codes 61-63, moderate continuous rain
- `heavy_rain` — WMO codes 65, 82, intense rainfall
- `freezing_rain` — WMO codes 56-57, rain that freezes on contact
- `snow` — WMO codes 71-73, 77, snowfall
- `heavy_snow` — WMO code 75, intense snowfall
- `rain_showers` — WMO codes 80-81, intermittent rain
- `snow_showers` — WMO codes 85-86, intermittent snow
- `thunderstorm` — WMO code 95, thunderstorm without hail
- `thunderstorm_with_hail` — WMO codes 96, 99, thunderstorm with hail
- `dust_storm` — Decoded from visibility and wind combination
- `haze` — Reduced visibility from atmospheric particles

**Used in tables:** weather_hourly_window, weather_daily_summaries

---

## 3.13 breach_level

**Purpose:** Severity classification when a measured value crosses a disaster threshold.

**Values and meaning:**
- `watch` — Value is approaching threshold, situation developing. Monitoring intensified but no action yet.
- `warning` — Value has crossed the warning threshold. Preparation and readiness actions begin.
- `emergency` — Value has crossed the critical threshold. Active response and evacuation may be required.
- `extreme` — Value has crossed the extreme threshold. Maximum response, catastrophic event.

**Used in tables:** weather_hourly_window, weather_daily_summaries, seismic_events, flood_gauge_current, flood_gauge_forecasts, threshold_breach_log

---

## 3.14 flood_status

**Purpose:** Google Flood Hub official flood severity classification for a river gauge.

**Values and meaning:**
- `no_flooding` — River level within normal range, no flood concern
- `watch` — River level elevated, potential for flooding, monitoring required
- `warning` — River level has reached warning threshold, flooding likely
- `emergency` — River level has reached danger threshold, active flooding or imminent

**Used in tables:** flood_gauge_current, flood_gauge_forecasts

---

## 3.15 river_trend

**Purpose:** Direction and rate of change of river water level.

**Values and meaning:**
- `rapidly_rising` — Level increasing more than 0.5 meters per hour
- `rising` — Level increasing between 0.1 and 0.5 meters per hour
- `stable` — Level changing less than 0.1 meters per hour in either direction
- `falling` — Level decreasing between 0.1 and 0.5 meters per hour
- `rapidly_falling` — Level decreasing more than 0.5 meters per hour

**Why this matters:** A river at 80% of danger level is very different depending on trend. If it is rapidly rising, emergency response should begin immediately. If it is rapidly falling, the peak has passed and recovery begins. The trend is often more actionable than the absolute level.

**Used in tables:** flood_gauge_current

---

## 3.16 magnitude_class

**Purpose:** Standard seismological classification of earthquake magnitude.

**Values and meaning:**
- `micro` — Magnitude below 2.0. Not felt by people. Detected only by instruments.
- `minor` — Magnitude 2.0 to 3.9. Felt by some people. No damage.
- `light` — Magnitude 4.0 to 4.9. Felt by many people. Minor damage possible in vulnerable buildings.
- `moderate` — Magnitude 5.0 to 5.9. Significant shaking. Damage to poorly constructed buildings.
- `strong` — Magnitude 6.0 to 6.9. Destructive in populated areas. Major damage to buildings.
- `major` — Magnitude 7.0 to 7.9. Serious damage over large areas. Many deaths possible.
- `great` — Magnitude 8.0 and above. Catastrophic destruction. Deaths in thousands.

**Used in tables:** seismic_events

---

## 3.17 depth_class

**Purpose:** Classification of earthquake depth which determines the pattern and extent of surface shaking.

**Values and meaning:**
- `shallow` — Depth 0 to 70 kilometers. Most destructive category. Energy released close to surface creates intense, focused shaking. The 2005 Kashmir earthquake was shallow.
- `intermediate` — Depth 70 to 300 kilometers. Shaking spread over wider area but less intense at any single point.
- `deep` — Depth greater than 300 kilometers. Often barely felt at surface despite potentially large magnitude.

**Used in tables:** seismic_events

---

## 3.18 seismic_data_quality

**Purpose:** USGS processing status indicating whether an earthquake record has been human-verified.

**Values and meaning:**
- `automatic` — Record was generated by seismic detection algorithms only. No human review. Magnitude and location may be preliminary estimates. Can change significantly in the hours following detection.
- `reviewed` — A USGS seismologist has examined the record and confirmed or corrected the automated values. This is the authoritative version.
- `deleted` — USGS determined this was a false detection (instrument malfunction, noise, quarry blast, etc.) and removed the event. Records with this status must be excluded from all analysis.

**Why this matters:** Your Risk Analysis Agent should weight reviewed events with much higher confidence than automatic events, and must completely ignore deleted events.

**Used in tables:** seismic_events

---

## 3.19 breach_dispatch_status

**Purpose:** Tracks whether a threshold breach has been successfully communicated to the main ClimaSync operational system.

**Values and meaning:**
- `pending` — Breach detected, waiting to be sent to main system
- `dispatched` — Successfully sent to main system, main system acknowledged receipt
- `suppressed` — This breach is a duplicate of a recent breach from the same location and metric, so it was not sent to avoid flooding the main system with duplicate alerts
- `dispatch_failed` — Attempted to send to main system but communication failed, will retry

**Used in tables:** threshold_breach_log

---

# SECTION 4: REFERENCE TABLES

## What Are Reference Tables

Reference tables store data that changes very rarely or never. They define the structure and configuration of your system. They are read frequently but written to infrequently. Examples include the list of monitoring locations, the configuration of external APIs, and the list of river gauges.

---

## 4.1 Table: api_registry

### Purpose
This table stores the configuration and live health state for each of the three external APIs your system uses. It is the central registry that the Data Collection Service reads before every API call to know rate limits, check health state, and determine if the API is in backoff mode.

### Why This Table Exists
Without this table, your rate limiting state would be lost every time the application server restarts. If the server restarts after hitting Open-Meteo's rate limit, the next startup would immediately hammer the API again and get blocked again. By persisting the rate limit state in the database, the service can read its own health state on startup and respect backoff periods even across restarts.

### Columns Explained

| Column | Type | Purpose |
|---|---|---|
| api_id | UUID | Primary key, uniquely identifies this API record |
| api_name | api_source_name | Which API this row represents (usgs, open_meteo, google_flood_hub) |
| display_name | VARCHAR | Human readable name shown in admin dashboard |
| base_url | TEXT | The root URL of this API for documentation reference |
| documentation_url | TEXT | Link to the API documentation for developer reference |
| max_requests_per_minute | INT | Rate limit imposed by the API provider |
| max_requests_per_day | INT | Daily quota imposed by the API provider |
| min_delay_between_calls_ms | INT | Minimum milliseconds to wait between consecutive calls to avoid triggering rate limits |
| initial_backoff_s | INT | When a 429 error occurs, wait this many seconds before retrying |
| max_backoff_s | INT | Maximum backoff duration regardless of how many retries have occurred |
| backoff_multiplier | DECIMAL | Each retry multiplies the backoff by this factor (exponential backoff) |
| current_health | api_health_state | Current health state updated after every cycle |
| last_success_at | TIMESTAMPTZ | When the last successful API call was made |
| last_failure_at | TIMESTAMPTZ | When the last failed API call occurred |
| consecutive_failures | SMALLINT | How many cycles in a row have failed, triggers escalating backoff |
| avg_latency_ms | INT | Rolling average response time for performance monitoring |
| rate_window_start_at | TIMESTAMPTZ | Start of the current rate limit counting window |
| calls_in_window | INT | Number of calls made within the current rate window |
| backoff_until | TIMESTAMPTZ | Do not make any calls to this API until this timestamp |
| is_active | BOOLEAN | Whether this API is currently enabled in the system |
| notes | TEXT | Any operational notes about this API for the team |

### Row Count
Exactly 3 rows. One per API. Never changes.

---

## 4.2 Table: pakistan_locations

### Purpose
This is the master geographic reference table for all 270 monitoring coordinate points across Pakistan. It serves two critical functions simultaneously. First, it is the polling configuration — the Data Collection Service reads this table to know which coordinates to call Open-Meteo for, in what priority order, and at what frequency. Second, it is the geographic reference — when USGS returns earthquake coordinates or when you need to know which district a location belongs to, this table provides the answer through spatial queries.

### Why This Table Exists
You cannot monitor all of Pakistan equally. You need a curated, thoughtful list of the most important points to monitor. This table encodes that knowledge. It also encodes the vulnerability context of each location — is this area flood prone? What is the building quality? How many people live here? — which the Risk Analysis Agent uses to compute disaster impact severity.

### Columns Explained

| Column | Type | Purpose |
|---|---|---|
| location_id | UUID | Primary key |
| location_key | VARCHAR(120) | Deterministic unique key in format "lahore_31.5497_74.3436". Used as cache keys and for joining with weather observation data |
| location_name | VARCHAR(255) | English name of the location |
| local_name | VARCHAR(255) | Urdu or regional language name for display in Pakistani context |
| location_tier | location_tier | Strategic classification of this location's importance |
| district | VARCHAR(100) | Administrative district this location belongs to |
| division | VARCHAR(100) | Administrative division (grouping of districts) |
| province | pk_province | Province this location belongs to |
| coordinates | GEOGRAPHY(POINT) | PostGIS point geometry for spatial calculations |
| latitude | DECIMAL(10,7) | Latitude in decimal degrees (also stored separately for fast access) |
| longitude | DECIMAL(10,7) | Longitude in decimal degrees |
| elevation_m | INT | Elevation above sea level in meters |
| population | BIGINT | Total population from latest census |
| population_density | DECIMAL(10,2) | Persons per square kilometer |
| flood_risk_zone | risk_zone | Pre-assessed flood risk level for this location |
| seismic_zone | VARCHAR(5) | Pakistan seismic zone designation (I, II, III, IV) |
| heat_risk_zone | risk_zone | Pre-assessed heat wave risk level |
| drought_risk_zone | risk_zone | Pre-assessed drought risk level |
| infrastructure_quality | vulnerability_level | Overall infrastructure quality assessment |
| drainage_quality | vulnerability_level | Quality of drainage infrastructure (critical for flood/rain risk) |
| building_stock | VARCHAR(50) | Predominant construction type: kutcha (mud), semi_pucca, pucca (brick/concrete), mixed |
| poll_priority | poll_priority | How urgently this location should be polled |
| poll_interval_minutes | INT | Target minutes between Open-Meteo API calls for this location |
| last_polled_at | TIMESTAMPTZ | When this location was last successfully polled |
| last_poll_outcome | poll_outcome | Result of the most recent poll attempt |
| next_poll_due_at | TIMESTAMPTZ | Calculated next scheduled poll time. Polling scheduler queries this column |
| consecutive_failures | SMALLINT | How many consecutive polls have failed. Used to deprioritize broken coordinates |
| is_active | BOOLEAN | Whether this location is currently being polled |
| data_source | VARCHAR(100) | Where this location's data came from (PBS census, OSM, NADRA, manual survey) |

### Row Count
Approximately 270 rows. Changes very rarely — only when new monitoring points are added or removed.

---

## 4.3 Table: pakistan_infrastructure

### Purpose
Stores individual critical infrastructure assets across Pakistan — hospitals, schools, bridges, dams, power stations, and evacuation centers. This table is used by the Risk Analysis Agent to assess the real-world impact of a disaster beyond just population count. A flood that threatens 3 hospitals and 15 schools is categorically more dangerous than a flood of the same size in an uninhabited area.

### Why This Table Exists
Population count alone is insufficient for disaster impact assessment. You need to know what critical services are at risk. If a hospital is within the earthquake impact zone, medical response capacity in the region is simultaneously destroyed at the moment it is most needed. This compound impact must be captured in the risk assessment.

### Columns Explained

| Column | Type | Purpose |
|---|---|---|
| asset_id | UUID | Primary key |
| location_id | UUID | Foreign key to nearest pakistan_locations entry. Links asset to monitoring zone |
| asset_name | VARCHAR(255) | Official name of the facility |
| asset_type | asset_type | Classification of this infrastructure |
| coordinates | GEOGRAPHY(POINT) | Exact location for spatial impact calculations |
| latitude | DECIMAL(10,7) | Latitude for quick access without spatial query |
| longitude | DECIMAL(10,7) | Longitude |
| district | VARCHAR(100) | Administrative district |
| province | pk_province | Province |
| capacity | INT | Service capacity in relevant units |
| capacity_unit | VARCHAR(30) | Unit for capacity: beds, students, MW, persons |
| vulnerability_score | DECIMAL(4,2) | Numeric vulnerability 0 to 10 where 10 is most vulnerable |
| vulnerability_level | vulnerability_level | Categorical vulnerability rating |
| is_seismic_resistant | BOOLEAN | Whether this building meets seismic construction standards |
| is_flood_resistant | BOOLEAN | Whether this facility has flood protection measures |
| is_critical | BOOLEAN | TRUE means this asset is unique or serves over 10,000 people. Critical assets receive special attention in risk analysis |
| serves_population | INT | Estimated population that depends on this facility |
| data_source | VARCHAR(100) | Data origin: NDMA, District Health Office, OSM, field survey |
| last_verified_at | TIMESTAMPTZ | When this record was last field-verified for accuracy |
| is_active | BOOLEAN | Whether this facility is currently operational |

### Row Count
Approximately 500 to 2,000 rows depending on data availability. Static reference data.

---

## 4.4 Table: disaster_thresholds

### Purpose
This is arguably the most strategically important reference table in the entire database. It stores Pakistan-specific, province-specific, and season-specific threshold values for every disaster metric your system monitors. When a weather observation or gauge reading arrives, the collection service compares it against this table to decide whether to trigger a breach alert.

### Why This Table Exists
Consider the difference: a maximum temperature of 44 degrees Celsius in Karachi in July is hot but not unusual — no alert needed. The same temperature in Murree in April is genuinely dangerous and abnormal — alert needed immediately. Without location-specific and season-specific thresholds, your system either misses real emergencies or generates endless false alarms. By externalizing all threshold logic into this table, thresholds can be updated by domain experts without changing any application code.

### Columns Explained

| Column | Type | Purpose |
|---|---|---|
| threshold_id | UUID | Primary key |
| disaster_kind | disaster_kind | Which disaster type this threshold applies to |
| metric_name | VARCHAR(100) | Standardized name of the measurement being thresholded. Examples: temp_max_c, precip_24h_mm, magnitude, gauge_pct_of_danger |
| province | pk_province | Province this threshold applies to. NULL means this is the national default |
| district | VARCHAR(100) | District this threshold applies to. NULL means province-wide |
| applies_season | VARCHAR(20) | Season this threshold applies to: monsoon, pre_monsoon, summer, winter. NULL means year-round |
| watch_threshold | DECIMAL(12,4) | Value at which monitoring intensifies. Not yet dangerous but developing |
| warning_threshold | DECIMAL(12,4) | Value at which preparatory actions should begin |
| emergency_threshold | DECIMAL(12,4) | Value at which active emergency response is required |
| extreme_threshold | DECIMAL(12,4) | Value indicating catastrophic conditions |
| breach_direction | VARCHAR(5) | 'above' means value exceeding threshold triggers breach (heat, rain, flood). 'below' means value dropping below threshold triggers breach (cold wave, drought) |
| unit | VARCHAR(30) | Unit of measurement for clarity: celsius, mm, km/h, richter, percent |
| description | TEXT | Plain English explanation of what this threshold represents |
| data_source | VARCHAR(100) | Authority behind these values: NDMA, Pakistan Meteorological Department, WMO, expert judgment |
| is_active | BOOLEAN | Whether this threshold is currently enforced |
| last_reviewed_at | TIMESTAMPTZ | When a domain expert last reviewed these values |

### How Threshold Lookup Works
When the collection service needs the temperature threshold for Punjab in monsoon season, it queries with this priority: first look for a district-specific monsoon threshold for Punjab. If not found, look for a province-wide Punjab monsoon threshold. If not found, look for a national monsoon threshold. If not found, look for the national year-round threshold. This cascading specificity means you can define very precise thresholds for high-risk areas while relying on sensible national defaults everywhere else.

### Row Count
Approximately 50 to 200 rows. Updated by disaster management domain experts when new data is available.

---

## 4.5 Table: flood_gauge_registry

### Purpose
Stores the static, permanent properties of every river gauge in Pakistan that Google Flood Hub monitors. Each physical gauge has exactly one row here. The properties stored — gauge location, river name, established threshold levels — come from WAPDA (Water and Power Development Authority) and NDMA and change very rarely.

### Why This Table Exists
Gauge readings and forecasts change constantly. But the gauge's physical location, the river it sits on, its official warning and danger thresholds — these are permanent facts about the physical infrastructure. Separating permanent gauge properties from time-varying readings is correct normalization. It also means when you want to find all gauges on the Indus river system, you query this table once rather than scanning millions of reading records.

### Columns Explained

| Column | Type | Purpose |
|---|---|---|
| gauge_id | UUID | Internal primary key |
| google_gauge_id | VARCHAR(100) | The unique identifier Google Flood Hub uses for this gauge. Used in all API calls |
| gauge_name | VARCHAR(255) | Official name of this gauge station |
| official_gauge_code | VARCHAR(50) | WAPDA or PMD official gauge code for cross-reference with government systems |
| river_name | VARCHAR(255) | Name of the river this gauge sits on |
| river_system | VARCHAR(100) | Major river system grouping: Indus, Jhelum-Chenab, Ravi-Sutlej, Kabul, Coastal |
| basin_name | VARCHAR(255) | Catchment basin name |
| upstream_area_sqkm | DECIMAL(12,2) | Total catchment area upstream of this gauge. Larger upstream area means more water converges here during rain events |
| coordinates | GEOGRAPHY(POINT) | Physical location of the gauge station |
| latitude | DECIMAL(10,7) | Latitude |
| longitude | DECIMAL(10,7) | Longitude |
| district | VARCHAR(100) | District where gauge is located |
| province | pk_province | Province |
| nearest_location_id | UUID | Foreign key to nearest pakistan_locations entry. Used to find population at risk near this gauge |
| normal_level_m | DECIMAL(8,3) | Typical river level in meters under normal conditions |
| bankfull_level_m | DECIMAL(8,3) | Level at which water reaches the top of the river bank. Flooding begins above this |
| warning_level_m | DECIMAL(8,3) | Official NDMA warning level in meters |
| danger_level_m | DECIMAL(8,3) | Official NDMA danger level in meters |
| extreme_level_m | DECIMAL(8,3) | Official extreme flood level in meters |
| historical_max_m | DECIMAL(8,3) | Highest ever recorded level at this gauge |
| poll_priority | poll_priority | How frequently to poll this gauge |
| is_active | BOOLEAN | Whether this gauge is currently operational and reporting |
| data_source | VARCHAR(100) | Data origin: WAPDA, PMD, Google |

### Row Count
Approximately 150 rows. Changes only when new gauges are commissioned or decommissioned.

---

# SECTION 5: OPERATIONAL TABLES

## What Are Operational Tables

Operational tables track the execution and health of the data collection process itself. They answer questions like: when did we last poll? How many locations succeeded? Is the USGS API healthy? These tables are essential for monitoring system health and debugging collection failures.

---

## 5.1 Table: collection_cycles

### Purpose
Records every single data collection cycle that the system executes. One row is created when a polling cycle begins and updated as the cycle progresses and completes. This table is your primary tool for answering: is the system working? When did it last successfully collect data? How many locations are failing?

### Why This Table Exists
Without this table, if your Open-Meteo data stops updating, you have no way to know whether the API is down, whether your code crashed, or whether the polling is simply slow. With this table, you can query the last completed cycle time, see the success rate, and immediately diagnose what is happening. It is your system health log.

### Columns Explained

| Column | Type | Purpose |
|---|---|---|
| cycle_id | UUID | Primary key |
| api_id | UUID | Foreign key to api_registry, identifies which API this cycle polled |
| api_name | api_source_name | Denormalized API name for fast queries without joining api_registry |
| cycle_type | VARCHAR(30) | Why this cycle was triggered: scheduled (routine), priority_refresh (urgent), manual (admin triggered), startup (system start), retry (previous cycle failed) |
| status | cycle_status | Current state of this cycle: running, completed, partial, failed, skipped |
| locations_targeted | INT | How many locations were supposed to be polled in this cycle |
| locations_success | INT | How many locations were successfully polled |
| locations_failed | INT | How many locations failed with an error |
| locations_skipped | INT | How many locations were intentionally skipped |
| rows_upserted | INT | How many existing rows were updated with fresh data |
| rows_inserted | INT | How many new rows were created (new forecast hours, new earthquake events) |
| rows_deleted | INT | How many expired rows were deleted during this cycle's cleanup phase |
| breaches_triggered | INT | How many threshold breaches were detected during this cycle |
| total_api_calls | INT | Total number of HTTP requests made to the API |
| rate_limit_hits | INT | How many times the API returned HTTP 429 during this cycle |
| total_bytes | BIGINT | Total bytes of API response data received |
| started_at | TIMESTAMPTZ | When this cycle began |
| completed_at | TIMESTAMPTZ | When this cycle finished (NULL while still running) |
| duration_ms | INT | Total cycle duration in milliseconds |
| avg_latency_ms | INT | Average API call response time in milliseconds |
| error_summary | JSONB | Dictionary mapping failed location keys to their error messages for debugging |
| failure_reason | TEXT | If the cycle failed entirely, what caused the failure |
| triggered_by | VARCHAR(50) | What triggered this cycle: scheduler, manual, threshold_breach, startup |
| server_id | VARCHAR(100) | Identifies which server instance ran this cycle (useful in multi-server deployments) |

---

# SECTION 6: TIME-SERIES TABLES

## What Are Time-Series Tables

Time-series tables store measurements that change over time. Each row represents a snapshot of conditions at a specific place and time. These are the largest tables in the database by row count and contain the actual disaster monitoring data.

---

## 6.1 Table: weather_hourly_window

### Purpose
This is the primary weather data table and the largest table in the database. It stores one row for every location for every hour within the 5-day window. Each row represents the weather conditions at a specific location at a specific hour — either what the weather currently is (for the present hour) or what it is forecast to be (for future hours).

### Why This Table Exists
Weather disasters — heatwaves, heavy rain, storms — develop over hours and days. To detect these events early and give people time to prepare, you need hour-by-hour forecast data for the next several days. When Open-Meteo says that Lahore will receive 80mm of rain between 6 PM and midnight on Thursday, your system needs to store that prediction today (Tuesday) and alert NGOs to prepare on Wednesday.

### The Upsert Mechanism
The primary key is the combination of location_id and forecast_for_datetime. This means there can only be one row per location per hour. When Open-Meteo is polled again 3 hours later with a fresher forecast for the same location and the same hours, those rows are updated not duplicated. This keeps the row count permanently bounded at 32,400 maximum.

### Columns Explained

**Identity and Source**

| Column | Type | Purpose |
|---|---|---|
| location_id | UUID | Part of composite primary key. Which location this row represents |
| forecast_for_datetime | TIMESTAMPTZ | Part of composite primary key. The specific hour this row represents in Pakistan time |
| forecast_date | DATE | Date portion of forecast_for_datetime in Pakistan time. Auto-computed by trigger |
| day_offset | SMALLINT | Days from today: 0=today, 1=tomorrow, up to 4. Auto-computed by trigger. Enforced to be within 0-4 range |
| location_key | VARCHAR(120) | Denormalized from pakistan_locations for fast access without join |
| location_name | VARCHAR(255) | Denormalized location name |
| district | VARCHAR(100) | Denormalized district |
| province | pk_province | Denormalized province |
| latitude | DECIMAL(10,7) | Denormalized latitude for frontend map rendering |
| longitude | DECIMAL(10,7) | Denormalized longitude |
| cycle_id | UUID | Which collection cycle wrote this row most recently |
| last_updated_at | TIMESTAMPTZ | When this row was last written. Used for data freshness assessment |
| data_freshness_minutes | INT | How many minutes late this data was collected versus its scheduled time |

**Temperature**

| Column | Type | Purpose |
|---|---|---|
| temp_c | DECIMAL(5,2) | Actual air temperature in Celsius at 2 meters height |
| temp_apparent_c | DECIMAL(5,2) | Feels-like temperature accounting for humidity and wind. More relevant for heatwave risk than actual temperature |
| temp_dewpoint_c | DECIMAL(5,2) | Dewpoint temperature. When dewpoint exceeds 26°C combined with high temperature, heat stress becomes medically dangerous |

**Precipitation**

| Column | Type | Purpose |
|---|---|---|
| precip_mm | DECIMAL(7,3) | Precipitation amount for this specific hour in millimeters |
| precip_prob_pct | SMALLINT | Probability (0-100) that precipitation occurs in this hour |
| rain_mm | DECIMAL(7,3) | Liquid rain component of precipitation |
| snowfall_cm | DECIMAL(6,3) | Snowfall component in centimeters |
| snow_depth_m | DECIMAL(6,3) | Total snow depth on ground in meters |
| precip_3h_mm | DECIMAL(8,3) | Sum of precipitation for this hour and the 2 preceding hours |
| precip_6h_mm | DECIMAL(8,3) | 6-hour rolling precipitation sum |
| precip_12h_mm | DECIMAL(9,3) | 12-hour rolling precipitation sum |
| precip_24h_mm | DECIMAL(9,3) | 24-hour rolling precipitation sum — the most important metric for flood risk assessment |
| precip_72h_mm | DECIMAL(10,3) | 72-hour rolling precipitation sum — critical for soil saturation and slow-onset flood risk |

**Wind**

| Column | Type | Purpose |
|---|---|---|
| wind_speed_kmh | DECIMAL(6,2) | Wind speed at 10 meters height in km/h |
| wind_gusts_kmh | DECIMAL(6,2) | Peak gust speed. Structural damage depends on gusts not average speed |
| wind_direction_deg | SMALLINT | Wind direction in degrees (0/360=North, 90=East, 180=South, 270=West) |
| wind_direction_cardinal | VARCHAR(3) | Human readable direction: N, NE, E, SE, S, SW, W, NW. Auto-computed by trigger |

**Atmospheric**

| Column | Type | Purpose |
|---|---|---|
| humidity_pct | SMALLINT | Relative humidity percentage |
| pressure_hpa | DECIMAL(8,2) | Atmospheric pressure in hectopascals |
| visibility_m | INT | Visibility distance in meters |
| cloud_cover_pct | SMALLINT | Percentage of sky covered by clouds |
| uv_index | DECIMAL(4,2) | UV radiation index. Above 11 is extreme, relevant for outdoor rescue workers |
| cape_jkg | DECIMAL(8,2) | Convective Available Potential Energy in Joules per kilogram. This is the most important severe storm predictor. Above 1000 = thunderstorm risk. Above 2500 = severe thunderstorm. Above 3500 = violent storms. Pakistan's most destructive flash floods are often CAPE-driven |

**Weather Classification**

| Column | Type | Purpose |
|---|---|---|
| weather_code | SMALLINT | Raw WMO weather interpretation code from Open-Meteo |
| weather_condition | weather_condition | Human-readable condition decoded from weather_code by trigger automatically |
| weather_description | VARCHAR(150) | Full text description for display |
| is_daytime | BOOLEAN | Whether this hour is during daylight in this location |

**Disaster Flags**

| Column | Type | Purpose |
|---|---|---|
| flag_extreme_heat | BOOLEAN | Temperature or feels-like exceeds extreme heat threshold for this location |
| flag_heatwave | BOOLEAN | Three or more consecutive days with temperature above heatwave threshold |
| flag_heavy_rain | BOOLEAN | Hourly or accumulated precipitation exceeds heavy rain threshold |
| flag_very_heavy_rain | BOOLEAN | Precipitation exceeds very heavy rain threshold (higher tier) |
| flag_storm | BOOLEAN | Thunderstorm weather code detected |
| flag_severe_storm | BOOLEAN | Thunderstorm code plus CAPE above 2500 J/kg |
| flag_cold_wave | BOOLEAN | Temperature below cold wave threshold for this location and season |
| flag_dust_storm | BOOLEAN | Dust storm weather condition detected |
| flag_dense_fog | BOOLEAN | Fog condition with visibility below 200 meters |

**Threshold Breach**

| Column | Type | Purpose |
|---|---|---|
| has_breach | BOOLEAN | Whether any disaster threshold is breached in this row. Primary filter column for breach detection queries |
| breach_severity | breach_level | Severity level of the breach: watch, warning, emergency, extreme |
| breach_metric | VARCHAR(100) | Which specific metric triggered the breach, e.g. precip_24h_mm |
| breach_observed_value | DECIMAL(12,4) | The actual measured or forecasted value that crossed the threshold |
| breach_threshold_value | DECIMAL(12,4) | The specific threshold value that was crossed |
| threshold_id | UUID | Foreign key to disaster_thresholds, identifying which threshold rule was triggered |

---

## 6.2 Table: weather_daily_summaries

### Purpose
Stores one daily summary row per location per day for all 5 days in the window. Where weather_hourly_window has hourly granularity (up to 120 rows per location), this table has daily granularity (5 rows per location). It comes directly from Open-Meteo's daily aggregation response and provides the day-level overview that the frontend forecast panel and the Risk Analysis Agent use for multi-day trend assessment.

### Why This Table Exists
When assessing heatwave risk, you need to know that the next 4 days will all have maximum temperatures above 45 degrees Celsius — a daily summary view is far more readable than scanning 96 hourly rows. When assessing multi-day flood risk, the daily precipitation total is the most actionable number. This table provides those daily aggregates directly from the API without requiring your system to compute them from hourly data.

### Columns Explained

| Column | Type | Purpose |
|---|---|---|
| location_id + summary_date | Composite PK | UPSERT key ensuring one row per location per day |
| day_offset | SMALLINT | Days from today (0-4). Auto-computed by trigger |
| location_key, location_name, district, province | VARCHAR | Denormalized for fast access |
| temp_max_c | DECIMAL(5,2) | Maximum temperature for the day |
| temp_min_c | DECIMAL(5,2) | Minimum temperature for the day |
| feels_like_max_c | DECIMAL(5,2) | Maximum feels-like temperature |
| feels_like_min_c | DECIMAL(5,2) | Minimum feels-like temperature |
| precip_total_mm | DECIMAL(9,3) | Total precipitation for the entire day — primary flood risk metric |
| rain_total_mm | DECIMAL(9,3) | Total liquid rain component |
| snowfall_total_cm | DECIMAL(8,3) | Total snowfall |
| precip_hours | SMALLINT | How many hours in this day have precipitation |
| precip_prob_max_pct | SMALLINT | Maximum precipitation probability across all hours of this day |
| wind_speed_max_kmh | DECIMAL(6,2) | Peak wind speed for the day |
| wind_gusts_max_kmh | DECIMAL(6,2) | Peak wind gust for the day |
| wind_dominant_cardinal | VARCHAR(3) | Predominant wind direction for the day |
| dominant_condition | weather_condition | Most representative weather condition for the day |
| uv_index_max | DECIMAL(4,2) | Maximum UV index during daylight hours |
| sunrise_at | TIMESTAMPTZ | Sunrise time in Pakistan timezone |
| sunset_at | TIMESTAMPTZ | Sunset time in Pakistan timezone |
| daylight_hours | DECIMAL(4,2) | Total daylight duration in hours |
| flag_extreme_heat_day | BOOLEAN | This day has extreme heat conditions |
| flag_heatwave_day | BOOLEAN | This day is part of a heatwave sequence |
| flag_heavy_rain_day | BOOLEAN | This day has heavy rain conditions |
| flag_storm_day | BOOLEAN | This day has storm conditions |
| flag_cold_wave_day | BOOLEAN | This day has cold wave conditions |
| worst_breach_severity | breach_level | The most severe breach recorded across any hour of this day |

---

## 6.3 Table: seismic_events

### Purpose
Stores every earthquake event detected by USGS within Pakistan's geographic bounding box during the 5-day window. Each earthquake gets exactly one row, identified by the USGS event ID. Because USGS continuously refines earthquake data — updating magnitude, felt reports, and alert levels for hours after an event — your system uses UPSERT on the USGS event ID. The row always reflects the current best USGS estimate.

### Why This Table Exists
Earthquake response is fundamentally different from weather response. You cannot predict when an earthquake will occur. You can only react to it immediately after detection. This table is the real-time earthquake situational awareness feed for Pakistan. When a magnitude 6.2 strikes near Quetta, this table has the record within 3 to 7 minutes of the physical event, and the row gets updated as USGS refines the estimate over the following hours.

### Columns Explained

**Identity**

| Column | Type | Purpose |
|---|---|---|
| event_id | UUID | Internal primary key |
| usgs_event_id | VARCHAR(50) | USGS unique identifier. THE key for upsert — if this ID already exists, update the row |
| usgs_event_url | TEXT | URL to the USGS event detail page for reference |

**Classification (auto-computed by triggers)**

| Column | Type | Purpose |
|---|---|---|
| magnitude | DECIMAL(4,2) | Earthquake magnitude on whatever scale USGS used |
| magnitude_type | VARCHAR(10) | Scale used: ml (local), mb (body wave), mw (moment tensor), ms (surface wave) |
| magnitude_class | magnitude_class | Category auto-assigned by trigger based on magnitude value |
| depth_km | DECIMAL(8,3) | Depth of earthquake hypocenter in kilometers |
| depth_class | depth_class | Shallow/intermediate/deep classification auto-assigned by trigger |

**Location**

| Column | Type | Purpose |
|---|---|---|
| coordinates | GEOGRAPHY(POINT) | Epicenter location for spatial queries |
| latitude | DECIMAL(10,7) | Epicenter latitude |
| longitude | DECIMAL(10,7) | Epicenter longitude |
| usgs_place | VARCHAR(500) | USGS human-readable location description |
| resolved_district | VARCHAR(100) | Pakistan district resolved from coordinates using spatial query against pakistan_locations |
| resolved_province | pk_province | Pakistan province resolved from coordinates |
| nearest_location_id | UUID | Foreign key to nearest monitoring location in pakistan_locations |
| distance_to_nearest_km | DECIMAL(8,2) | Distance from epicenter to nearest monitoring location |

**Impact Data**

| Column | Type | Purpose |
|---|---|---|
| felt_reports | INT | Number of people who reported feeling this earthquake through USGS Did You Feel It system |
| cdi | DECIMAL(4,2) | Community Decimal Intensity — average shaking intensity reported by the public on 0-10 scale |
| mmi | DECIMAL(4,2) | Modified Mercalli Intensity from USGS ShakeMap — estimated maximum shaking intensity at ground level |
| tsunami_flag | BOOLEAN | USGS tsunami flag. TRUE means a tsunami warning may have been issued |
| usgs_alert_level | VARCHAR(10) | PAGER system alert: green (minimal impact), yellow (limited impact), orange (significant impact), red (widespread casualties) |
| significance | INT | USGS significance score 0-1000 combining magnitude, felt reports, and estimated impact |

**Data Quality**

| Column | Type | Purpose |
|---|---|---|
| station_count | SMALLINT | Number of seismograph stations that contributed to this location estimate. More stations means better accuracy |
| azimuthal_gap_deg | DECIMAL(6,2) | Largest gap in station coverage around the epicenter in degrees. Values above 180 mean the location estimate is unreliable |
| rms_seconds | DECIMAL(6,4) | Root mean square of timing residuals. Higher values indicate less precise location |
| data_quality | seismic_data_quality | Whether this data is automatic (algorithm), reviewed (human verified), or deleted (false detection) |
| contributing_networks | TEXT[] | Array of seismic network codes that detected this event |

**USGS Update Tracking**

| Column | Type | Purpose |
|---|---|---|
| initial_magnitude | DECIMAL(4,2) | What the magnitude was when our system first detected this event. Preserved even after USGS updates it |
| magnitude_was_revised | BOOLEAN | TRUE if USGS has updated the magnitude since our system first saw this event. Auto-set by trigger |
| usgs_last_updated_at | TIMESTAMPTZ | When USGS last modified this event record |

**Timestamps**

| Column | Type | Purpose |
|---|---|---|
| earthquake_time | TIMESTAMPTZ | The actual physical time the earthquake occurred, from USGS |
| first_seen_at | TIMESTAMPTZ | When our system first detected this event in USGS feed |
| last_refreshed_at | TIMESTAMPTZ | When our system last updated this row with fresh USGS data |

**Raw Data**

| Column | Type | Purpose |
|---|---|---|
| raw_api_response | JSONB | Complete USGS GeoJSON feature object preserved as-is. If we later realize we forgot to extract a field, this allows backfilling without re-calling the API |

---

## 6.4 Table: flood_gauge_current

### Purpose
Stores the most recent river gauge reading for every active gauge. This table has exactly one row per gauge — it always represents the current situation right now. When a new reading arrives, the existing row is completely overwritten. There is no history here. Only the present state.

### Why This Table Exists
For flood response, what you care about most is what the river level is right now and which direction it is trending. Is the Indus at Sukkur currently rising toward the danger level? How fast? How many hours until it reaches danger threshold if the current rise rate continues? This table answers all of those questions instantly with a simple primary key lookup on the gauge_id.

### Columns Explained

| Column | Type | Purpose |
|---|---|---|
| gauge_id | UUID | Primary key — also the unique identifier. One row per gauge always |
| google_gauge_id | VARCHAR(100) | Denormalized Google identifier for fast API correlation |
| gauge_name | VARCHAR(255) | Denormalized gauge name |
| river_name | VARCHAR(255) | Denormalized river name |
| river_system | VARCHAR(100) | Denormalized river system grouping |
| district + province | VARCHAR | Denormalized administrative context |
| reading_time | TIMESTAMPTZ | Timestamp of the actual gauge measurement |
| current_level_m | DECIMAL(8,3) | Current river water level in meters |
| warning_level_m | DECIMAL(8,3) | Warning threshold copied from gauge_registry at write time for fast access |
| danger_level_m | DECIMAL(8,3) | Danger threshold copied from gauge_registry |
| extreme_level_m | DECIMAL(8,3) | Extreme threshold copied from gauge_registry |
| pct_of_warning | DECIMAL(7,3) | Current level as percentage of warning level. 100% means at warning level, 150% means 50% above warning |
| pct_of_danger | DECIMAL(7,3) | Current level as percentage of danger level — the most watched metric |
| pct_of_historical_max | DECIMAL(7,3) | Current level compared to highest ever recorded level at this gauge |
| previous_level_m | DECIMAL(8,3) | River level from the reading that this one replaces |
| level_change_m | DECIMAL(8,4) | Difference between current and previous level |
| rise_rate_m_per_hour | DECIMAL(8,4) | Rate of level change per hour, computed from level change and time difference |
| river_trend | river_trend | Direction classification: rapidly_rising, rising, stable, falling, rapidly_falling |
| hours_to_warning | DECIMAL(8,2) | Projected hours until river reaches warning level at current rise rate. NULL if falling or already above warning |
| hours_to_danger | DECIMAL(8,2) | Projected hours until river reaches danger level |
| flood_status | flood_status | Official Google Flood Hub classification: no_flooding, watch, warning, emergency |
| has_breach | BOOLEAN | Whether this gauge is currently in breach of a disaster threshold |
| breach_severity | breach_level | Severity of current breach |
| raw_api_response | JSONB | Complete API response for this reading |
| collected_at | TIMESTAMPTZ | When our system wrote this row |

---

## 6.5 Table: flood_gauge_forecasts

### Purpose
Stores probabilistic river level forecasts for each gauge for each hour over the 5-day window. Unlike flood_gauge_current which has one row per gauge, this table has up to 120 rows per gauge — one for each forecast hour. The UPSERT key is the combination of gauge_id and forecast_for_datetime.

### Why This Table Exists
The most valuable thing about Google Flood Hub is not the current reading — it is the forecast. If the forecast shows an 80% probability that the Jhelum at Trimmu will exceed danger level in 48 hours, NGOs should begin pre-positioning boats, food, and medicine today. This table is what enables the proactive and pre-active capabilities of ClimaSync that distinguish it from reactive systems.

### Why Probabilistic Forecasts Matter
Google Flood Hub does not give you a single predicted level. It gives you three: p10 (10th percentile — the optimistic scenario), p50 (median — the most likely scenario), and p90 (90th percentile — the pessimistic scenario). This matters enormously for decision making. A p50 level below warning but a p90 level above danger means there is a 10% chance of a very serious event. You should prepare for that possibility even though the most likely outcome is manageable.

### Columns Explained

| Column | Type | Purpose |
|---|---|---|
| gauge_id + forecast_for_datetime | Composite PK | UPSERT key. One row per gauge per forecast hour |
| forecast_date | DATE | Date of this forecast in Pakistan time. Auto-computed by trigger |
| day_offset | SMALLINT | Days from today (0-4). Auto-computed by trigger |
| forecast_horizon_h | INT | Hours from now until this forecast's valid time. Auto-computed by trigger |
| google_gauge_id | VARCHAR(100) | Denormalized |
| river_name | VARCHAR(255) | Denormalized |
| district + province | VARCHAR | Denormalized administrative context |
| forecast_issued_at | TIMESTAMPTZ | When Google generated this forecast |
| last_updated_at | TIMESTAMPTZ | When our system last wrote this row |
| level_p10_m | DECIMAL(8,3) | 10th percentile predicted river level. Only 10% chance actual level is below this |
| level_p50_m | DECIMAL(8,3) | Median predicted river level. This is the most likely outcome |
| level_p90_m | DECIMAL(8,3) | 90th percentile predicted level. 90% chance actual level stays below this |
| prob_exceeds_warning_pct | DECIMAL(5,2) | Probability (0-100%) that the actual level will exceed the warning threshold |
| prob_exceeds_danger_pct | DECIMAL(5,2) | Probability that actual level will exceed danger threshold. The most critical metric for pre-activation |
| prob_exceeds_extreme_pct | DECIMAL(5,2) | Probability that actual level will exceed extreme threshold |
| forecast_status | flood_status | Status classification based on p50 level |
| worst_case_status | flood_status | Status classification based on p90 level — the pessimistic scenario |
| has_forecast_breach | BOOLEAN | Whether the p50 forecast exceeds a disaster threshold |
| breach_severity | breach_level | Severity of the forecast breach |

---

# SECTION 7: ALERT OUTPUT TABLE

## 7.1 Table: threshold_breach_log

### Purpose
This is the output channel of the entire data collection database. When the collection service detects that any observed or forecasted value has crossed a disaster threshold, it writes a record to this table. The main ClimaSync operational system continuously monitors this table and picks up these breach records to create formal alerts and activate the Verification Agent pipeline.

Think of this table as the **alarm bell**. Every row here represents a potential disaster situation that needs attention.

### Why This Table Exists
You need a clean, structured interface between the data collection system and the main operational system. Rather than having the main system query all weather, seismic, and flood tables looking for dangerous conditions, the collection service does that work and writes a simple, structured notification here. The main system only needs to watch this one table.

### The Duplicate Suppression Mechanism
If Lahore's temperature is 47 degrees Celsius for 6 consecutive hours, that would generate 6 separate breach records without suppression logic. You do not want 6 alerts for the same ongoing condition. The is_duplicate and duplicate_of_breach_id columns implement suppression — only the first breach per location per metric within a configurable suppression window gets dispatched. Subsequent breaches during the same event are marked as duplicates and suppressed.

### Columns Explained

| Column | Type | Purpose |
|---|---|---|
| breach_id | UUID | Primary key |
| source_api | api_source_name | Which API produced the data that triggered this breach |
| weather_location_id | UUID | For weather breaches: the location_id from pakistan_locations |
| weather_datetime | TIMESTAMPTZ | For weather breaches: the forecast_for_datetime of the triggering row |
| seismic_event_id | UUID | For earthquake breaches: foreign key to seismic_events |
| gauge_id | UUID | For flood breaches: foreign key to flood_gauge_registry |
| is_forecast_breach | BOOLEAN | FALSE means the breach is in current observed data happening now. TRUE means the breach is in forecast data — a future event warning |
| forecast_horizon_h | INT | For forecast breaches: how many hours until this forecasted breach materialises |
| threshold_id | UUID | Which disaster threshold was crossed |
| disaster_kind | disaster_kind | Type of disaster this breach represents |
| metric_name | VARCHAR(100) | Which specific measurement triggered the breach |
| location_name | VARCHAR(255) | Denormalized location for main system consumption |
| district | VARCHAR(100) | Denormalized district |
| province | pk_province | Denormalized province |
| latitude | DECIMAL(10,7) | Denormalized coordinates |
| longitude | DECIMAL(10,7) | Denormalized coordinates |
| coordinates | GEOGRAPHY(POINT) | PostGIS point for spatial queries in main system |
| observed_value | DECIMAL(12,4) | The actual value that crossed the threshold |
| threshold_value | DECIMAL(12,4) | The threshold that was crossed |
| breach_severity | breach_level | How severe the breach is |
| excess_amount | DECIMAL(12,4) | How much the observed value exceeded the threshold |
| excess_pct | DECIMAL(8,4) | Excess as percentage of threshold |
| observation_time | TIMESTAMPTZ | When the triggering observation was recorded |
| is_duplicate | BOOLEAN | Whether this breach was suppressed as a duplicate |
| duplicate_of_breach_id | UUID | Which earlier breach this duplicates |
| suppression_window_used_m | INT | The suppression window in minutes that was applied |
| dispatch_status | breach_dispatch_status | Current dispatch state |
| dispatched_at | TIMESTAMPTZ | When this breach was successfully sent to the main system |
| main_system_alert_id | UUID | The alert ID created in the main ClimaSync database for correlation |
| dispatch_attempt_count | SMALLINT | How many times dispatch has been attempted |
| last_dispatch_error | TEXT | Error message from last failed dispatch attempt |
| detected_at | TIMESTAMPTZ | When our collection service detected this breach |

---

# SECTION 8: TRIGGERS

## What Are Triggers and Why Use Them

A trigger is a function that PostgreSQL executes automatically when a specific event happens on a table — an INSERT, UPDATE, or DELETE. Triggers enforce data integrity and automate computations at the database level. This means the computation happens regardless of which application, script, or tool writes the data. A trigger cannot be bypassed by mistake.

---

## Trigger 1 — compute_magnitude_class

**Fires on:** INSERT or UPDATE of magnitude column on seismic_events

**What it does:** Automatically assigns the magnitude_class enum value based on the magnitude number. If magnitude is 6.3 it automatically sets magnitude_class to strong. No application code needs to implement this logic.

**Why a trigger:** This classification must be consistent regardless of how the row is written. Whether data comes from the Python collection service, a manual SQL insert, or a data import script, the classification will always be correct.

---

## Trigger 2 — compute_depth_class

**Fires on:** INSERT or UPDATE of depth_km column on seismic_events

**What it does:** Automatically assigns depth_class as shallow (0-70km), intermediate (70-300km), or deep (300+km) based on the depth_km value.

---

## Trigger 3 — decode_wmo_code

**Fires on:** INSERT or UPDATE of weather_code column on weather_hourly_window

**What it does:** Translates the numeric WMO weather code from Open-Meteo into a human-readable weather_condition enum value. WMO code 65 automatically becomes heavy_rain. WMO code 99 automatically becomes thunderstorm_with_hail.

**Why a trigger:** WMO codes are numeric and meaningless to humans. The translation must happen at write time so views and queries can filter on the readable category directly.

---

## Trigger 4 — compute_wind_cardinal

**Fires on:** INSERT or UPDATE of wind_direction_deg column on weather_hourly_window

**What it does:** Converts the numeric wind direction in degrees to a cardinal direction label. 45 degrees automatically becomes NE. 225 degrees automatically becomes SW.

---

## Trigger 5 — compute_weather_day_offset

**Fires on:** INSERT or UPDATE of forecast_for_datetime column on weather_hourly_window

**What it does:** Automatically computes forecast_date (the date in Pakistan timezone) and day_offset (0 for today, 1 for tomorrow, etc.) from the forecast_for_datetime timestamp. Also enforces the 5-day window — if you attempt to insert a row with a date before today or more than 4 days ahead, the trigger raises an exception and rejects the insert.

**Why a trigger:** The day_offset is used heavily in queries and indexes. Computing it automatically at write time means it is always accurate and never needs to be manually maintained.

---

## Trigger 6 — compute_daily_summary_offset

**Fires on:** INSERT or UPDATE of summary_date column on weather_daily_summaries

**What it does:** Same as Trigger 5 but for the daily summaries table. Computes day_offset from the summary_date and enforces the 5-day window boundary.

---

## Trigger 7 — compute_flood_forecast_offset

**Fires on:** INSERT or UPDATE of forecast_for_datetime column on flood_gauge_forecasts

**What it does:** Computes forecast_date, day_offset, and forecast_horizon_h automatically from the forecast timestamp. Enforces the 5-day window boundary for flood forecasts.

---

## Trigger 8 — sync_location_poll_state

**Fires on:** INSERT on a location poll log (conceptually after each Open-Meteo poll completes)

**What it does:** Updates the pakistan_locations row for the polled location with last_polled_at, last_poll_outcome, next_poll_due_at, and consecutive_failures. If the poll succeeded, consecutive_failures resets to 0 and next_poll_due_at is set to now plus poll_interval_minutes. If the poll failed, consecutive_failures increments.

**Why a trigger:** The polling scheduler needs to read next_poll_due_at from pakistan_locations to know what to poll next. This state must be kept accurate after every poll. A trigger guarantees this happens atomically with the poll result.

---

## Trigger 9 — sync_api_health_on_cycle

**Fires on:** UPDATE of status column on collection_cycles

**What it does:** When a collection cycle transitions from running to completed, partial, or failed, this trigger updates the api_registry row for that API. It updates current_health, last_success_at, last_failure_at, consecutive_failures, and the exponential moving average of avg_latency_ms.

**Why a trigger:** API health state in api_registry must always reflect the outcome of the most recent cycle. Without this trigger, a developer would need to remember to update api_registry after every cycle completion — an easy thing to forget that would leave health state permanently stale.

---

## Trigger 10 — track_magnitude_revision

**Fires on:** UPDATE of magnitude column on seismic_events

**What it does:** The first time USGS updates an earthquake's magnitude, this trigger saves the original magnitude into initial_magnitude and sets magnitude_was_revised to TRUE. Subsequent magnitude updates do not overwrite initial_magnitude — only the first revision is recorded.

**Why a trigger:** USGS frequently revises magnitudes significantly in the first hour after an earthquake. Knowing that an event was initially reported as 5.8 but revised to 6.3 is important context for understanding the alert timeline and the quality of initial response decisions.

---

# SECTION 9: VIEWS

## What Are Views and Why Use Them

A view is a saved query that you can query like a table. Views serve two purposes. First, they present pre-joined, pre-filtered data in a format that is directly useful to the application or agent without requiring complex queries every time. Second, they enforce a separation between raw data storage and data presentation — the underlying tables can be restructured and the view updated without changing any application code.

---

## View 1 — current_weather_per_location

**Purpose:** Shows the most recent weather conditions for every active monitoring location. Returns one row per location.

**What it does:** For each location, finds the most recent weather_hourly_window row with day_offset=0 (today). Joins with pakistan_locations to add vulnerability context. Computes data_age_minutes and a data_freshness label (fresh, stale, very_stale).

**Who uses it:** Frontend map to render the temperature and weather condition overlay. Risk Analysis Agent to get current weather context for all locations quickly.

---

## View 2 — weather_5day_forecast_per_location

**Purpose:** Shows the daily weather forecast summary for every location across all 5 days.

**What it does:** Reads from weather_daily_summaries and adds day labels (Today, Tomorrow, specific day name). Ordered by location then day_offset.

**Who uses it:** Frontend forecast panel showing the 5-day outlook per district. Pre-activation assessment for upcoming heat waves or heavy rain events.

---

## View 3 — significant_recent_earthquakes

**Purpose:** Shows all magnitude 4.0 and above earthquakes from the last 5 days that have not been deleted by USGS.

**What it does:** Filters seismic_events to significant events only. Joins with pakistan_locations to add nearest city population context. Computes hours_since_event. Joins with threshold_breach_log to show dispatch status.

**Who uses it:** Frontend seismic awareness panel. Verification Agent receiving earthquake breach alerts. Admin dashboard for situational awareness.

---

## View 4 — flood_situation_current

**Purpose:** Complete real-time flood situational dashboard showing every active gauge with context, trend, and forecast.

**What it does:** Reads flood_gauge_current for the current state of each gauge. Joins flood_gauge_registry for static properties. Joins pakistan_locations for population at risk. Uses lateral joins to pull the closest available 24-hour and 72-hour forecast values for each gauge from flood_gauge_forecasts.

**Who uses it:** Frontend flood dashboard. Risk Analysis Agent for flood impact assessment. Work Distributor Agent for resource pre-positioning decisions.

---

## View 5 — active_breach_summary

**Purpose:** Lists all currently active threshold breaches that have not yet been dispatched to the main system or whose dispatch failed.

**What it does:** Reads threshold_breach_log filtered to non-duplicate, pending or failed dispatch records. Joins disaster_thresholds for threshold context. Joins pakistan_locations for vulnerability context. Ordered by severity then detection time.

**Who uses it:** Dispatch service that sends breaches to the main ClimaSync system. Admin monitoring panel showing pending alerts.

---

## View 6 — pakistan_risk_heatmap

**Purpose:** Provides one comprehensive risk row per monitoring location combining weather, seismic, and flood data into a single composite risk score.

**What it does:** For each location in pakistan_locations, pulls current weather from current_weather_per_location view, pulls worst upcoming weather breach from weather_daily_summaries, finds the nearest significant earthquake using spatial distance ordering, finds the nearest flood gauge status using spatial distance ordering, and computes a composite_risk_score from 0 to 4 by taking the maximum across all three data source breach severity levels. Also produces a human-readable composite_risk_label.

**Who uses it:** Frontend interactive risk map where each location is colored by risk level. The composite score drives the color from green (normal) through yellow (watch) and orange (warning) to red (emergency/extreme). Risk Analysis Agent for initial multi-hazard assessment.

---

## View 7 — collection_health_dashboard

**Purpose:** Real-time health status of all three APIs and their most recent collection cycle.

**What it does:** Reads api_registry for health state, rate limit status, and backoff information. Uses a lateral join to pull the most recent collection_cycles record for each API. Computes is_in_backoff, backoff_remaining_seconds, minutes_since_last_success, and last cycle success rate.

**Who uses it:** Admin monitoring panel. Automated alerting if any API has been down for more than N minutes. Development debugging when collection is not working as expected.

---

## View 8 — undispatched_breaches

**Purpose:** Shows the queue of breach alerts waiting to be sent to the main ClimaSync system, ordered by priority.

**What it does:** Reads threshold_breach_log filtered to pending and dispatch_failed records that are not duplicates. Joins disaster_thresholds for unit and threshold context. Builds a dispatch_payload JSONB column containing all the information the main system needs to create an alert record, pre-assembled as a JSON object so the dispatch service can send it directly without additional queries.

**Who uses it:** The dispatch service that polls this view every 30 seconds and sends each payload to the main ClimaSync FastAPI endpoint. The pre-assembled dispatch_payload column means the dispatch service is simple — read the view, POST the payload, update the status.

---

# SECTION 10: CLEANUP FUNCTION

## 10.1 Function: cleanup_expired_window_data

### Purpose
This function implements the rolling 5-day window by deleting all rows that belong to dates before today in Pakistan time. It runs once daily, ideally at midnight Pakistan time via pg_cron scheduled job.

### What It Deletes
- **weather_hourly_window:** All rows where forecast_date is before today in Pakistan time
- **weather_daily_summaries:** All rows where summary_date is before today in Pakistan time
- **seismic_events:** All rows where the earthquake occurred more than 5 days ago in Pakistan time
- **flood_gauge_forecasts:** All rows where forecast_date is before today in Pakistan time
- **threshold_breach_log:** All rows that have been dispatched and are older than 5 days

### What It Does Not Delete
- **flood_gauge_current:** Never deleted. Always exactly one row per gauge representing the current state
- **Reference tables:** api_registry, pakistan_locations, pakistan_infrastructure, disaster_thresholds, flood_gauge_registry are permanent reference data

### Return Value
The function returns a result set showing how many rows were deleted from each table. This allows your monitoring system to verify the cleanup ran and detect any unexpected deletion counts.

### Schedule
Run at 00:05 PKT daily. The 5-minute offset from midnight ensures that any data from the last hour of the expiring day has been fully collected and processed before deletion begins.

---

# SECTION 11: DESIGN PRINCIPLES SUMMARY

```
┌─────────────────────────────────────────────────────────────────┐
│  PRINCIPLE 1: BOUNDED SIZE                                      │
│  Maximum 52,500 rows total. Never grows.                        │
│  Predictable storage. Consistently fast queries.                │
├─────────────────────────────────────────────────────────────────┤
│  PRINCIPLE 2: UPSERT NOT ACCUMULATE                             │
│  Weather and flood forecasts overwrite old rows.                │
│  Only earthquake events and breach log accumulate               │
│  within the 5-day window.                                       │
├─────────────────────────────────────────────────────────────────┤
│  PRINCIPLE 3: COMPUTED AT WRITE TIME                            │
│  Triggers compute classifications, offsets, and                 │
│  cardinals at insert time. Queries never compute them.          │
│  Read performance maximized.                                    │
├─────────────────────────────────────────────────────────────────┤
│  PRINCIPLE 4: DENORMALIZE FOR TIME-SERIES PERFORMANCE           │
│  Location name, district, province are copied into              │
│  every time-series row. JOIN cost eliminated from               │
│  the most frequently executed queries.                          │
├─────────────────────────────────────────────────────────────────┤
│  PRINCIPLE 5: CLEAN HANDOFF                                     │
│  threshold_breach_log is the single output channel.             │
│  Main system watches one table. Collection system               │
│  manages everything else independently.                         │
├─────────────────────────────────────────────────────────────────┤
│  PRINCIPLE 6: PAKISTAN TIME EVERYWHERE                          │
│  Database timezone set to Asia/Karachi.                         │
│  All date calculations use Pakistan time.                       │
│  Window boundaries respect Pakistan midnight.                   │
├─────────────────────────────────────────────────────────────────┤
│  PRINCIPLE 7: RAW DATA PRESERVED                                │
│  Every table stores the complete raw API response               │
│  in a JSONB column. If a field is missed during                 │
│  development, it can be backfilled from raw_api_response        │
│  without re-calling the API.                                    │
└─────────────────────────────────────────────────────────────────┘
```