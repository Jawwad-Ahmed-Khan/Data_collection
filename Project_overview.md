# ClimaSync.ai — Data Collection Service
## Complete Technical Documentation

---

> **Document Type:** Technical Reference Document
> **Scope:** Data Collection Service — Complete System Documentation
> **Version:** 1.0
> **Project:** ClimaSync.ai — AI-Powered Disaster Management Platform

---

# PART 1: PROJECT CONTEXT

---

## 1.1 What ClimaSync.ai Is

ClimaSync.ai is an AI-powered disaster management platform designed specifically for Pakistan. The platform addresses the critical gap that exists between disaster occurrence and organized response. Currently in Pakistan, disaster management systems are disconnected, reactive, and post-hoc. NGOs duplicate efforts, resources are wasted, early warnings generate false alarms, and coordination between government bodies and relief organizations is fragmented.

ClimaSync.ai solves this by introducing an autonomous multi-agent AI system that monitors disaster conditions continuously, verifies incoming alerts automatically, assesses risk using local population and infrastructure data, generates actionable safety plans, distributes tasks to NGOs intelligently, and communicates with the public through social media — all without requiring manual human intervention for routine operations.

## 1.2 Pakistan Disaster Context

Pakistan is ranked the fourth most exposed country to floods globally. The 2022 floods displaced 8 million people, affected approximately 33 million, and caused damages exceeding USD 30 billion. In 2025, monsoon floods displaced 2.5 million people in Punjab alone, killed over 600 people, and destroyed thousands of homes, with rainfall 10 to 15 percent heavier than historical averages due to climate change. Pakistan also sits on multiple active seismic fault lines including the Chaman Fault, the Makran Subduction Zone, and the Himalayan collision boundary, making it highly vulnerable to earthquakes. Heat waves in interior Sindh regularly exceed 50 degrees Celsius, claiming hundreds of lives annually.

## 1.3 The Seven Agents of ClimaSync.ai

ClimaSync.ai operates through seven specialized AI agents, each with a specific role:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CLIMASYNC AGENT PIPELINE                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1: Data Collection Agent Service                                   │
│  Role: Monitors USGS, Open-Meteo, Google Flood Hub continuously     │
│  Type: Automated service (not LLM-based)                            │
│  Output: Structured data in collection database + breach alerts     │
│                                                                     │
│  AGENT 1: Verification Agent                                        │
│  Role: Confirms disaster data is real and not a false alarm         │
│  Type: OpenAI Agents SDK (GPT-4o)                                   │
│  Input: Breach alerts from collection database                      │
│  Output: Verified or rejected alert status                          │
│                                                                     │
│  AGENT 2: Risk Analysis Agent                                       │
│  Role: Assesses severity using population and infrastructure data   │
│  Type: OpenAI Agents SDK (GPT-4o)                                   │
│  Input: Verified disaster events                                    │
│  Output: Severity scores, risk levels, impact estimates             │
│                                                                     │
│  AGENT 3: Precaution Definer Agent                                  │
│  Role: Generates actionable safety and response plans               │
│  Type: OpenAI Agents SDK (GPT-4o)                                   │
│  Input: Risk assessment results                                     │
│  Output: Structured precautionary steps and resource requirements   │
│                                                                     │
│  AGENT 4: Work Distributor Agent                                    │
│  Role: Categorizes and routes tasks to appropriate agents           │
│  Type: OpenAI Agents SDK (GPT-4o-mini)                              │
│  Input: Precaution plans                                            │
│  Output: Routed tasks to Task Allocator and Social Media agents     │
│                                                                     │
│  AGENT 5: Task Allocator Agent                                      │
│  Role: Assigns tasks to NGOs based on resources and location        │
│  Type: OpenAI Agents SDK (GPT-4o)                                   │
│  Input: Tasks from Work Distributor                                 │
│  Output: NGO assignments with notifications                         │
│                                                                     │
│  AGENT 6: Social Media Agent                                        │
│  Role: Creates and posts automated public awareness alerts          │
│  Type: OpenAI Agents SDK (GPT-4o-mini)                              │
│  Input: Verified disaster events and precautions                    │
│  Output: Published posts on Twitter, Facebook, LinkedIn             │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## 1.4 Scope of This Document

This document covers **only — the Data Collection Service**. All other agents are outside the scope of this document. The Data Collection Service is the foundation upon which all other agents depend. Without accurate, timely, and well-structured data collection, no other agent can function correctly.

---

# PART 2: DATA COLLECTION SERVICE OVERVIEW

---

## 2.1 What the Data Collection Service Is

The Data Collection Service is a continuously running Python backend application built with FastAPI. It is not an LLM-powered AI agent. It is a deterministic, scheduled, rule-based service that executes a defined workflow repeatedly and reliably.

The service has one fundamental job: **watch Pakistan for disaster conditions around the clock and immediately alert the main ClimaSync system when dangerous thresholds are crossed.**

It does this by:
- Polling three external APIs on defined schedules
- Parsing and storing structured data in a dedicated database
- Comparing every new data point against Pakistan-specific disaster thresholds
- Detecting threshold breaches and recording them
- Dispatching breach notifications to the main ClimaSync operational system

## 2.2 Why It Is a Separate Service

The Data Collection Service runs as a completely separate application from the main ClimaSync backend. This separation exists for several important reasons.

**Reliability isolation:** If the data collection service encounters a problem, the main operational system continues running. NGOs can still access their tasks, administrators can still view the dashboard, and the system remains functional. The reverse is also true — if the main system has a deployment or update, data collection continues uninterrupted.

**Independent scaling:** Data collection is IO-bound work — it spends most of its time waiting for API responses. The main operational system is compute-bound when running AI agents. These different workload profiles benefit from independent resource allocation.

**Technology fit:** A continuously running scheduler-based service has different operational characteristics than a request-response API. Separating them allows each to be optimized for its own workload.

**Storage separation:** Time-series weather and seismic data grows at a predictable rate and requires different query patterns than operational data like user accounts, tasks, and NGO profiles. Separate databases allow independent optimization.

## 2.3 What the Service Produces

The Data Collection Service produces two types of outputs:

**Stored data:** Structured, cleaned, validated disaster-monitoring data stored in the collection database. This includes hourly weather forecasts for 15 monitoring locations, current earthquake events in Pakistan, river gauge readings and flood forecasts for major Pakistani rivers.

**Breach alerts:** When any measured or forecasted value crosses a predefined disaster threshold, the service creates a breach record and dispatches it to the main ClimaSync system. This is the primary trigger for the entire downstream agent pipeline.

## 2.4 Disaster Types Monitored

```
┌────────────────────────────────────────────────────────────────┐
│              DISASTER TYPES AND DATA SOURCES                   │
├────────────────┬───────────────────────┬───────────────────────┤
│  DISASTER TYPE │  DATA SOURCE          │  DETECTION METHOD     │
├────────────────┼───────────────────────┼───────────────────────┤
│  Earthquake    │  USGS Earthquake API  │  Magnitude threshold  │
│  Flood         │  Google Flood Hub     │  Gauge level % danger │
│  Flash Flood   │  Open-Meteo           │  Precip accumulation  │
│  Heat Wave     │  Open-Meteo           │  Max temp threshold   │
│  Heavy Rain    │  Open-Meteo           │  Hourly/24h precip    │
│  Cyclone       │  Open-Meteo           │  Wind speed + CAPE    │
│  Cold Wave     │  Open-Meteo           │  Min temp threshold   │
│  Dust Storm    │  Open-Meteo           │  Weather code + wind  │
│  Landslide     │  Open-Meteo           │  Rain + terrain risk  │
│  Drought       │  Open-Meteo           │  Precip deficit       │
└────────────────┴───────────────────────┴───────────────────────┘
```

---

# PART 3: TECHNICAL ARCHITECTURE

---

## 3.1 Technology Stack

```
┌──────────────────────────────────────────────────────────────────┐
│                    TECHNOLOGY STACK                              │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Language:           Python 3.12+                                │
│                                                                  │
│  Web Framework:      FastAPI                                     │
│  Why FastAPI:        Async support, automatic API docs,          │
│                      Pydantic integration, production-ready      │
│                                                                  │
│  ASGI Server:        Uvicorn                                     │
│  Why Uvicorn:        High performance async server for FastAPI   │
│                                                                  │
│  Package Manager:    UV                                          │
│  Why UV:             10-100x faster than pip, lockfile support,  │
│                      automatic virtual env management            │
│                                                                  │
│  Database Driver:    asyncpg                                     │
│  Why asyncpg:        Native async PostgreSQL, fastest Python     │
│                      PostgreSQL driver available                 │
│                                                                  │
│  HTTP Client:        httpx                                       │
│  Why httpx:          Async HTTP, timeout control, retry support  │
│                                                                  │
│  Scheduler:          APScheduler                                 │
│  Why APScheduler:    Supports interval + cron triggers,          │
│                      async-compatible, robust error handling      │
│                                                                  │
│  Data Validation:    Pydantic v2                                 │
│  Why Pydantic:       Type safety, automatic validation,          │
│                      JSON parsing, settings management           │
│                                                                  │
│  Retry Logic:        Tenacity                                    │
│  Why Tenacity:       Declarative retry with exponential backoff, │
│                      clean code without manual retry loops       │
│                                                                  │
│  Database:           PostgreSQL via Supabase                     │
│  Extensions:         PostGIS (geographic queries)                │
│                      pgcrypto (UUID generation)                  │
│                      citext (case-insensitive text)              │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

## 3.2 Architectural Pattern

The service follows a strict **Controller → Service → Repository → Database** layered architecture:

```
┌─────────────────────────────────────────────────────────────────┐
│                   LAYERED ARCHITECTURE                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  HTTP REQUEST                                                   │
│       ↓                                                         │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  CONTROLLER LAYER  (app/api/routes/)                    │    │
│  │  health_controller.py  |  status_controller.py          │    │
│  │  ─────────────────────────────────────────────────────  │    │
│  │  Receives HTTP requests                                 │    │
│  │  Validates input parameters                             │    │
│  │  Calls the appropriate service                          │    │
│  │  Returns HTTP responses                                 │    │
│  │  Contains NO business logic                             │    │
│  │  Contains NO database queries                           │    │
│  └────────────────────────┬────────────────────────────────┘    │
│                           ↓                                     │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  SERVICE LAYER  (app/services/)                         │    │
│  │  usgs_service  |  openmeteo_service  |  floodhub_service│    │
│  │  breach_service  |  dispatch_service                    │    │
│  │  ─────────────────────────────────────────────────────  │    │
│  │  Contains ALL business logic                            │    │
│  │  Makes ALL decisions                                    │    │
│  │  Orchestrates multiple repositories                     │    │
│  │  Calls external APIs through collectors                 │    │
│  │  Contains NO SQL queries                                │    │
│  │  Contains NO HTTP route handling                        │    │
│  └────────────────────────┬────────────────────────────────┘    │
│                           ↓                                     │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  REPOSITORY LAYER  (app/repositories/)                  │    │
│  │  seismic_repo  |  weather_repo  |  flood_repo           │    │
│  │  breach_repo   |  cycle_repo    |  reference_repo       │    │
│  │  ─────────────────────────────────────────────────────  │    │
│  │  ONLY talks to database                                 │    │
│  │  Executes SQL queries                                   │    │
│  │  Returns clean Pydantic model objects                   │    │
│  │  Contains NO business logic                             │    │
│  │  Contains NO HTTP handling                              │    │
│  └────────────────────────┬────────────────────────────────┘    │
│                           ↓                                     │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  DATABASE CONNECTION  (app/database/)                   │    │
│  │  connection.py  |  queries/                             │    │
│  │  ─────────────────────────────────────────────────────  │    │
│  │  Manages asyncpg connection pool                        │    │
│  │  All SQL strings stored in queries/ folder              │    │
│  │  Sets timezone to Asia/Karachi on every connection      │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  COLLECTOR LAYER  (app/collectors/)                             │
│  base_collector  |  usgs  |  openmeteo  |  floodhub             │
│  ─────────────────────────────────────────────────────────────  │
│  Makes HTTP calls to external APIs                              │
│  Handles rate limiting and retry logic                          │
│  Passes raw responses to service layer                          │
│  Manages collection cycle tracking                              │
│                                                                 │
│  SCHEDULER LAYER  (app/scheduler/)                              │
│  job_scheduler.py                                               │
│  ─────────────────────────────────────────────────────────────  │
│  Runs all collectors on defined intervals                       │
│  Runs breach dispatcher every 30 seconds                        │
│  Runs daily cleanup at midnight PKT                             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 3.3 Complete Project File Structure

```
Collection_Service/
│
├── app/
│   ├── __init__.py
│   ├── main.py
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── security.py
│   │   ├── logger.py
│   │   └── exceptions.py
│   │
│   ├── database/
│   │   ├── __init__.py
│   │   ├── connection.py
│   │   └── queries/
│   │       ├── __init__.py
│   │       ├── seismic_queries.py
│   │       ├── weather_queries.py
│   │       ├── flood_queries.py
│   │       ├── breach_queries.py
│   │       ├── cycle_queries.py
│   │       └── reference_queries.py
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── seismic_models.py
│   │   ├── weather_models.py
│   │   ├── flood_models.py
│   │   ├── breach_models.py
│   │   ├── cycle_models.py
│   │   └── reference_models.py
│   │
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── base_repository.py
│   │   ├── seismic_repository.py
│   │   ├── weather_repository.py
│   │   ├── flood_repository.py
│   │   ├── breach_repository.py
│   │   ├── cycle_repository.py
│   │   └── reference_repository.py
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── usgs_service.py
│   │   ├── openmeteo_service.py
│   │   ├── floodhub_service.py
│   │   ├── breach_service.py
│   │   └── dispatch_service.py
│   │
│   ├── collectors/
│   │   ├── __init__.py
│   │   ├── base_collector.py
│   │   ├── usgs_collector.py
│   │   ├── openmeteo_collector.py
│   │   └── floodhub_collector.py
│   │
│   ├── scheduler/
│   │   ├── __init__.py
│   │   └── job_scheduler.py
│   │
│   └── api/
│       ├── __init__.py
│       └── routes/
│           ├── __init__.py
│           ├── health_controller.py
│           └── status_controller.py
│
├── tests/
│   ├── __init__.py
│   ├── test_usgs_collector.py
│   ├── test_weather_collector.py
│   ├── test_flood_collector.py
│   └── test_breach_detection.py
│
├── .env
├── .env.example
├── .gitignore
├── pyproject.toml
├── uv.lock
└── README.md
```

---

# PART 4: DATABASE ARCHITECTURE

---

## 4.1 Two Database Strategy

ClimaSync.ai uses two completely separate Supabase PostgreSQL databases:

```
┌─────────────────────────────────────────────────────────────────┐
│  DATABASE 1: Main Operational Database (climasync-main)         │
│  Purpose: Users, NGOs, Tasks, Alerts, Social Posts              │
│  Used by: Main ClimaSync FastAPI backend                        │
│  Tables: 18 operational tables                                  │
│  Size: Grows with user activity                                 │
├─────────────────────────────────────────────────────────────────┤
│  DATABASE 2: Collection Database (climasync-collection)         │
│  Purpose: Weather, Seismic, Flood monitoring data               │
│  Used by: Data Collection Service exclusively                   │
│  Tables: 12 tables                                              │
│  Size: Fixed maximum ~52,500 rows (rolling window)              │
└─────────────────────────────────────────────────────────────────┘
```

## 4.2 Rolling 5-Day Window Design

The collection database does not accumulate data indefinitely. It maintains a rolling 5-day window — today plus the next 4 days. When tomorrow arrives, yesterday's data is deleted and day 5 is added. This design provides:

- **Bounded size:** Maximum 52,500 rows total, never grows beyond this
- **Consistent performance:** Queries always fast regardless of runtime duration
- **Relevant data:** Only current conditions and near-future forecasts stored
- **Low storage cost:** Fits comfortably in Supabase free tier

```
┌──────────────────────────────────────────────────────────────────┐
│  ROLLING WINDOW EXAMPLE — 15 July 2025                          │
├──────────────────────────────────────────────────────────────────┤
│  Day 0 → 15 July  (Today — current observed conditions)         │
│  Day 1 → 16 July  (Tomorrow — forecast)                         │
│  Day 2 → 17 July  (Forecast)                                    │
│  Day 3 → 18 July  (Forecast)                                    │
│  Day 4 → 19 July  (Forecast)                                    │
│                                                                  │
│  On 16 July at midnight PKT:                                    │
│  → 15 July data DELETED                                         │
│  → 20 July data ADDED                                           │
│  → Window always contains exactly 5 days                        │
└──────────────────────────────────────────────────────────────────┘
```

## 4.3 Database Table Summary

```
┌──────────────────────────────────────────────────────────────────┐
│              COLLECTION DATABASE — ALL 12 TABLES                 │
├────────────────────────┬────────────┬────────────────────────────┤
│  TABLE NAME            │  MAX ROWS  │  PURPOSE                   │
├────────────────────────┼────────────┼────────────────────────────┤
│  REFERENCE TABLES (5)  │            │                            │
│  api_registry          │  3         │  API config + health state  │
│  pakistan_locations    │  15*       │  Monitoring points + config │
│  pakistan_infrastructure│ ~500      │  Hospitals, schools, bridges│
│  disaster_thresholds   │  ~100      │  Pakistan breach limits     │
│  flood_gauge_registry  │  ~150      │  River gauge static data    │
├────────────────────────┼────────────┼────────────────────────────┤
│  OPERATIONAL TABLE (1) │            │                            │
│  collection_cycles     │  ~100 act. │  Polling cycle health log   │
├────────────────────────┼────────────┼────────────────────────────┤
│  TIME-SERIES (5)       │            │                            │
│  weather_hourly_window │  32,400    │  Hourly weather per location│
│  weather_daily_summaries│ 1,350     │  Daily weather per location │
│  seismic_events        │  75        │  Earthquakes in Pakistan    │
│  flood_gauge_current   │  150       │  Current river gauge state  │
│  flood_gauge_forecasts │  18,000    │  5-day flood forecast       │
├────────────────────────┼────────────┼────────────────────────────┤
│  ALERT OUTPUT (1)      │            │                            │
│  threshold_breach_log  │  ~500      │  Breach dispatch queue      │
├────────────────────────┼────────────┼────────────────────────────┤
│  TOTAL MAXIMUM         │  ~52,500   │                            │
└────────────────────────┴────────────┴────────────────────────────┘
* 15 locations for prototype, expandable to 270 later
```

## 4.4 Database Enums (17 Total)

The collection database uses 17 enum types for controlled vocabularies:

```
api_source_name:        usgs | open_meteo | google_flood_hub
api_health_state:       healthy | degraded | rate_limited | down | unknown
cycle_status:           running | completed | partial | failed | skipped
poll_outcome:           success | failed | rate_limited | timeout |
                        invalid_response | skipped
pk_province:            punjab | sindh | khyber_pakhtunkhwa |
                        balochistan | gilgit_baltistan |
                        azad_kashmir | islamabad_capital_territory
location_tier:          tier_1_provincial_capital |
                        tier_2_district_headquarters |
                        tier_3_disaster_zone | tier_3_river_basin |
                        tier_3_coastal | tier_3_mountain | tier_3_border
poll_priority:          critical | high | medium | low
asset_type:             hospital | basic_health_unit | school | bridge |
                        dam | barrage | power_station | water_treatment |
                        airport | flood_shelter | evacuation_center
vulnerability_level:    very_low | low | moderate | high |
                        very_high | critical
risk_zone:              zone_1_low | zone_2_moderate | zone_3_high |
                        zone_4_very_high | zone_5_critical
disaster_kind:          earthquake | flood | flash_flood | heatwave |
                        cyclone | heavy_rain | drought | landslide |
                        dust_storm | cold_wave
weather_condition:      clear | partly_cloudy | overcast | fog |
                        drizzle | rain | heavy_rain | freezing_rain |
                        snow | heavy_snow | rain_showers | snow_showers |
                        thunderstorm | thunderstorm_with_hail |
                        dust_storm | haze
breach_level:           watch | warning | emergency | extreme
flood_status:           no_flooding | watch | warning | emergency
river_trend:            rapidly_rising | rising | stable |
                        falling | rapidly_falling
magnitude_class:        micro | minor | light | moderate |
                        strong | major | great
depth_class:            shallow | intermediate | deep
seismic_data_quality:   automatic | reviewed | deleted
breach_dispatch_status: pending | dispatched | suppressed | dispatch_failed
```

## 4.5 Database Triggers (10 Total)

The database uses 10 automated triggers that fire on data changes:

```
┌──────────────────────────────────────────────────────────────────┐
│                    DATABASE TRIGGERS                             │
├────────────────────────────┬─────────────────────────────────────┤
│  TRIGGER                   │  WHAT IT DOES AUTOMATICALLY         │
├────────────────────────────┼─────────────────────────────────────┤
│  compute_magnitude_class   │  Sets magnitude_class enum from     │
│                            │  magnitude number on seismic_events │
│                            │  5.5 → moderate, 6.3 → strong       │
├────────────────────────────┼─────────────────────────────────────┤
│  compute_depth_class       │  Sets depth_class from depth_km     │
│                            │  0-70km → shallow (most dangerous)  │
│                            │  70-300km → intermediate            │
│                            │  300+km → deep                      │
├────────────────────────────┼─────────────────────────────────────┤
│  decode_wmo_code           │  Converts WMO weather code number   │
│                            │  to weather_condition enum          │
│                            │  Code 65 → heavy_rain               │
│                            │  Code 99 → thunderstorm_with_hail   │
├────────────────────────────┼─────────────────────────────────────┤
│  compute_wind_cardinal     │  Converts wind_direction_deg to     │
│                            │  cardinal: 45° → NE, 225° → SW      │
├────────────────────────────┼─────────────────────────────────────┤
│  compute_weather_day_offset│  Sets day_offset (0-4) and          │
│                            │  forecast_date from datetime        │
│                            │  Also enforces 5-day window         │
│                            │  Rejects rows outside window        │
├────────────────────────────┼─────────────────────────────────────┤
│  compute_daily_sum_offset  │  Same as above for daily summaries  │
├────────────────────────────┼─────────────────────────────────────┤
│  compute_flood_fc_offset   │  Sets day_offset, forecast_date,    │
│                            │  forecast_horizon_h for flood       │
│                            │  forecast records                   │
├────────────────────────────┼─────────────────────────────────────┤
│  sync_location_poll_state  │  After each weather poll completes, │
│                            │  updates pakistan_locations with    │
│                            │  last_polled_at, next_poll_due_at,  │
│                            │  consecutive_failures               │
├────────────────────────────┼─────────────────────────────────────┤
│  sync_api_health_on_cycle  │  When cycle completes, updates      │
│                            │  api_registry with health state,    │
│                            │  consecutive_failures, latency avg  │
├────────────────────────────┼─────────────────────────────────────┤
│  track_magnitude_revision  │  When USGS updates magnitude,       │
│                            │  saves original in initial_magnitude│
│                            │  sets magnitude_was_revised = TRUE  │
└────────────────────────────┴─────────────────────────────────────┘
```

## 4.6 Database Views (8 Total)

Eight pre-built views provide ready-to-query aggregated data:

```
┌──────────────────────────────────────────────────────────────────┐
│                    DATABASE VIEWS                                │
├────────────────────────────────┬─────────────────────────────────┤
│  VIEW NAME                     │  PURPOSE                        │
├────────────────────────────────┼─────────────────────────────────┤
│  current_weather_per_location  │  Most recent weather per        │
│                                │  location with freshness info   │
│                                │  Used by: Frontend map          │
├────────────────────────────────┼─────────────────────────────────┤
│  weather_5day_forecast         │  Daily summaries all 5 days     │
│  _per_location                 │  per location with day labels   │
│                                │  Used by: Frontend forecast     │
├────────────────────────────────┼─────────────────────────────────┤
│  significant_recent_           │  M4.0+ earthquakes last 5 days  │
│  earthquakes                   │  with location context          │
│                                │  Used by: Frontend seismic panel│
├────────────────────────────────┼─────────────────────────────────┤
│  flood_situation_current       │  Current state all active       │
│                                │  gauges with 24h and 72h        │
│                                │  forecast context               │
│                                │  Used by: Frontend flood panel  │
├────────────────────────────────┼─────────────────────────────────┤
│  active_breach_summary         │  All active threshold breaches  │
│                                │  with full threshold and        │
│                                │  location vulnerability context │
│                                │  Used by: Verification Agent    │
├────────────────────────────────┼─────────────────────────────────┤
│  pakistan_risk_heatmap         │  Composite risk score per       │
│                                │  location combining weather,    │
│                                │  seismic, and flood signals     │
│                                │  Used by: Frontend risk map     │
├────────────────────────────────┼─────────────────────────────────┤
│  collection_health_dashboard   │  Real-time API health status    │
│                                │  with last cycle stats          │
│                                │  Used by: Admin monitoring      │
├────────────────────────────────┼─────────────────────────────────┤
│  undispatched_breaches         │  Breach alerts pending          │
│                                │  dispatch with pre-built        │
│                                │  dispatch payload JSON          │
│                                │  Used by: Dispatch service      │
└────────────────────────────────┴─────────────────────────────────┘
```

---

# PART 5: EXTERNAL API INTEGRATION

---

## 5.1 USGS Earthquake API

### What It Is
The United States Geological Survey provides a public, free, no-authentication earthquake data API. It returns real-time earthquake detections worldwide in GeoJSON format.

### Endpoint Used
```
Base URL: https://earthquake.usgs.gov/fdsnws/event/1/query
Format:   GeoJSON
Method:   GET
Auth:     None required
```

### Query Parameters for Pakistan
```
format:        geojson
minmagnitude:  2.5
starttime:     [now - 6 hours]  ← 6-hour overlap catches USGS updates
endtime:       [now]
minlatitude:   23.0             ← Pakistan bounding box
maxlatitude:   38.0
minlongitude:  60.0
maxlongitude:  78.0
orderby:       time
```

### What USGS Returns
Each earthquake in the response contains:

```
PROPERTIES OBJECT:
  mag           → Magnitude value (e.g., 5.8)
  magType       → Scale used: ml, mb, mw, ms, md
  place         → Human text: "23km NNE of Muzaffarabad, Pakistan"
  time          → Unix milliseconds of earthquake occurrence
  updated       → Unix milliseconds of last USGS update to this record
  felt          → Number of public felt reports (can be NULL initially)
  cdi           → Community Decimal Intensity 0-10 (NULL initially)
  mmi           → Modified Mercalli Intensity 0-10 (NULL initially)
  alert         → PAGER alert: green/yellow/orange/red (NULL initially)
  status        → "automatic" or "reviewed" or "deleted"
  tsunami       → 0 or 1
  sig           → Significance score 0-1000
  net           → Network code: "us", "ak", "ci"
  nst           → Number of stations used
  dmin          → Minimum station distance in degrees
  rms           → Root mean square timing residuals
  gap           → Azimuthal gap in degrees (>180 = less reliable)
  type          → Always "earthquake"

GEOMETRY OBJECT:
  coordinates   → [longitude, latitude, depth_in_km]
```

### Critical USGS Behavior: Data Refinement
USGS continuously updates earthquake records after initial detection. A typical timeline:

```
T+0:00  Earthquake occurs
T+2:30  USGS publishes: magnitude 5.8, status "automatic"
T+0:45  First update: magnitude revised to 6.1, still "automatic"
T+2:00  Second update: status changes to "reviewed"
T+4:00  CDI and MMI values populate as felt reports arrive
T+12:00 PAGER alert level populates after impact assessment
T+24:00 Final authoritative record established
```

Your system uses UPSERT on usgs_event_id. The same event arrives multiple times with evolving data. Each UPSERT overwrites the row with the latest USGS values. The track_magnitude_revision trigger records the first revision.

### Polling Frequency
Every 5 minutes. This gives earthquake-to-system detection time of 7 to 10 minutes total (USGS processing 2-5 minutes plus your polling interval up to 5 minutes).

### Rate Limits
USGS is very generous — approximately 60 requests per minute. With one call per 5 minutes you will never hit limits.

---

## 5.2 Open-Meteo Weather API

### What It Is
Open-Meteo is a free, open-source weather API that provides hourly and daily weather forecasts for any coordinate on Earth. It requires no API key for the free tier.

### Endpoint Used
```
Base URL: https://api.open-meteo.com/v1/forecast
Method:   GET
Auth:     None for free tier
```

### Query Parameters for Each Location
```
latitude:     [location latitude]
longitude:    [location longitude]
timezone:     Asia/Karachi
forecast_days: 5
wind_speed_unit: kmh
precipitation_unit: mm

hourly: [
  temperature_2m,          apparent_temperature,
  dew_point_2m,            precipitation_probability,
  precipitation,           rain,
  snowfall,                snow_depth,
  weather_code,            pressure_msl,
  cloud_cover,             visibility,
  wind_speed_10m,          wind_direction_10m,
  wind_gusts_10m,          relative_humidity_2m,
  uv_index,                cape,
  is_day
]

daily: [
  weather_code,            temperature_2m_max,
  temperature_2m_min,      apparent_temperature_max,
  apparent_temperature_min, precipitation_sum,
  rain_sum,                snowfall_sum,
  precipitation_hours,     precipitation_probability_max,
  wind_speed_10m_max,      wind_gusts_10m_max,
  wind_direction_10m_dominant, uv_index_max,
  sunrise,                 sunset,
  daylight_duration
]
```

### What Open-Meteo Returns

One API call for one location returns:

```
HOURLY DATA:
  One array per variable, each with 120 values
  (24 hours × 5 days = 120 data points)
  Index 0 = first hour of today
  Index 119 = last hour of day 4

DAILY DATA:
  One array per variable, each with 5 values
  Index 0 = today
  Index 4 = day 4

METADATA:
  latitude, longitude, elevation, timezone,
  generationtime_ms (API processing time)
```

### Critical Open-Meteo Variables

**CAPE (Convective Available Potential Energy)** is the most important severe storm predictor and is rarely captured by other systems:
```
CAPE < 100 J/kg   → No significant storms
CAPE 100-1000     → Thunderstorm possible
CAPE 1000-2500    → Thunderstorm likely
CAPE 2500-3500    → Severe thunderstorm
CAPE > 3500       → Violent storms, flash flood risk
```

**WMO Weather Codes** are decoded by trigger:
```
0         → clear
1-2       → partly_cloudy
3         → overcast
45,48     → fog
51-55     → drizzle
56-57     → freezing_rain
61,63     → rain
65        → heavy_rain
71-77     → snow/heavy_snow
80-82     → rain_showers/heavy showers
85-86     → snow_showers
95        → thunderstorm
96,99     → thunderstorm_with_hail
```

### Rolling Accumulation Calculation
For flood risk assessment, 24-hour and 72-hour precipitation sums are more important than hourly values. These are computed from existing database rows when each new hourly row is stored:

```
precip_3h_mm  = SUM of precip_mm for this hour and 2 prior hours
precip_6h_mm  = SUM of precip_mm for this hour and 5 prior hours
precip_12h_mm = SUM of precip_mm for this hour and 11 prior hours
precip_24h_mm = SUM of precip_mm for this hour and 23 prior hours
precip_72h_mm = SUM of precip_mm for this hour and 71 prior hours
```

### Polling Strategy for 15 Locations
```
CHALLENGE:
  15 locations × 1 API call each = 15 calls per cycle
  Open-Meteo free tier: 10 requests per minute max
  15 calls at 500ms delay = 7.5 seconds total
  Well within rate limits

DELAY BETWEEN CALLS:
  500ms (0.5 seconds) between each location
  Prevents burst requests that trigger 429 errors
  Total cycle time: ~7.5 seconds for all 15 locations

FREQUENCY:
  Poll every 3-6 hours per location
  Scheduler runs check every 2 hours
  Each location's next_poll_due_at controls when it is polled
  Not all 15 polled every 2 hours — only those due

PRIORITY ORDER:
  critical locations polled first (provincial capitals)
  high priority second (major cities)
  medium priority third (disaster zones)
```

### Rate Limit Handling
```
On HTTP 429 received:
  1. Read Retry-After header (if present)
  2. Calculate backoff: initial_backoff_s × (multiplier ^ consecutive_failures)
  3. Cap at max_backoff_s
  4. Update api_registry.backoff_until = now + backoff_seconds
  5. All subsequent calls check backoff_until before executing
  6. Log the rate limit event with details
```

---

## 5.3 Google Flood Hub API

### What It Is
Google Flood Hub is an AI-powered flood forecasting service that provides river gauge readings and probabilistic flood forecasts for rivers worldwide including Pakistan's major river systems.

### Endpoints Used
```
Base URL: https://floodhub.googleapis.com/v1
Auth:     Google Cloud API key required

Current gauge reading:
  GET /gauges/{google_gauge_id}

Gauge forecast:
  GET /gauges/{google_gauge_id}/forecasts

List gauges in region:
  GET /gauges?parent=regions/PAK
```

### Pakistan River Systems Covered
```
INDUS MAIN STEM:
  Tarbela Dam, Kalabagh, Chashma,
  Taunsa Barrage, Guddu Barrage, Sukkur Barrage

JHELUM RIVER:
  Mangla Dam, Rasul Headworks

CHENAB RIVER:
  Marala Headworks, Trimmu Headworks

RAVI RIVER:
  Jassar, Shahdara (Lahore)

SUTLEJ RIVER:
  Suleimanki, Islam Headworks

KABUL RIVER:
  Warsak Dam, Nowshera

SWAT RIVER:
  Munda Headworks
```

### What Current Reading Returns
```
gauge_id:         google_gauge_id string
river_name:       name of river
location:         {latitude, longitude}
current_level_m:  current water level in meters
reading_time:     timestamp of measurement
flood_status:     no_flooding | watch | warning | emergency
```

### What Forecast Returns
```
For each future time step:
  valid_time:             timestamp of this forecast step
  level_p10_m:            10th percentile (optimistic)
  level_p50_m:            50th percentile (most likely)
  level_p90_m:            90th percentile (pessimistic)

Derived (computed by your system):
  prob_exceeds_warning:   probability of exceeding warning level
  prob_exceeds_danger:    probability of exceeding danger level
  prob_exceeds_extreme:   probability of exceeding extreme level
```

### Why Probabilistic Forecasts Matter
```
SCENARIO: Jhelum River at Mangla, 48-hour forecast
  level_p10_m: 7.2m (warning level is 8.0m, danger is 10.0m)
  level_p50_m: 8.5m (above warning — most likely outcome)
  level_p90_m: 10.8m (above danger level)
  prob_exceeds_danger: 12%

INTERPRETATION:
  Most likely: warning level exceeded → prepare
  12% chance: danger level exceeded → stage boats and food
  NGOs should pre-position TODAY not wait for the flood

This is the PRE-ACTIVE capability that distinguishes ClimaSync
from reactive post-disaster systems.
```

### Derived Metrics Computed by Service
```
pct_of_warning = (current_level / warning_level) × 100
pct_of_danger  = (current_level / danger_level) × 100
level_change_m = current_level - previous_level
rise_rate_m_per_hour = level_change / time_since_previous_reading
hours_to_warning = (warning_level - current) / rise_rate (if rising)
hours_to_danger  = (danger_level - current) / rise_rate (if rising)

river_trend classification:
  rise_rate > 0.5 m/h   → rapidly_rising
  rise_rate 0.1 to 0.5  → rising
  rise_rate -0.1 to 0.1 → stable
  rise_rate -0.5 to -0.1→ falling
  rise_rate < -0.5       → rapidly_falling
```

---

# PART 6: THRESHOLD BREACH DETECTION

---

## 6.1 How Threshold Detection Works

After every new data point is stored, the breach service compares the observed value against the disaster_thresholds table. If the value crosses any threshold level, a breach record is created.

## 6.2 Threshold Priority Lookup

Pakistan-specific thresholds are loaded with geographic and seasonal specificity. When evaluating a breach, the system looks for the most specific applicable threshold:

```
PRIORITY ORDER (most specific to least specific):

1. District + Season specific
   Example: Lahore district, monsoon season, temp_max_c threshold

2. District + Year-round
   Example: Lahore district, any season, temp_max_c threshold

3. Province + Season specific
   Example: Punjab province, monsoon season, temp_max_c threshold

4. Province + Year-round
   Example: Punjab province, any season, temp_max_c threshold

5. National + Season specific
   Example: National, monsoon season, temp_max_c threshold

6. National + Year-round
   Example: National default, any season, temp_max_c threshold

If no threshold found at any level: no breach check performed
```

## 6.3 Breach Severity Levels

```
┌──────────────────────────────────────────────────────────────────┐
│                    BREACH SEVERITY LEVELS                        │
├─────────────┬────────────────────────────────────────────────────┤
│  watch      │  Value approaching threshold. Situation            │
│             │  developing but not yet dangerous. Monitoring      │
│             │  intensified. No immediate action required.        │
├─────────────┼────────────────────────────────────────────────────┤
│  warning    │  Value has crossed warning threshold. Preparatory  │
│             │  actions should begin. NGOs should be on standby.  │
│             │  Public awareness posts may be issued.             │
├─────────────┼────────────────────────────────────────────────────┤
│  emergency  │  Critical threshold crossed. Active emergency      │
│             │  response required. Task allocation begins.        │
│             │  Evacuation may be ordered.                        │
├─────────────┼────────────────────────────────────────────────────┤
│  extreme    │  Catastrophic conditions. Maximum response.        │
│             │  All available resources mobilized. Mass           │
│             │  evacuation in progress.                           │
└─────────────┴────────────────────────────────────────────────────┘
```

## 6.4 Threshold Values — Pakistan Defaults

```
EARTHQUAKE THRESHOLDS (national, year-round):
  metric: magnitude
  watch:     4.0  (light — felt by many, minor damage possible)
  warning:   5.0  (moderate — significant damage in poor buildings)
  emergency: 6.0  (strong — destructive in populated areas)
  extreme:   7.0  (major — serious damage over large area)
  direction: above

HEATWAVE THRESHOLDS (national default, summer):
  metric: temp_max_c
  watch:     40°C
  warning:   44°C
  emergency: 47°C
  extreme:   50°C
  direction: above

HEATWAVE (Sindh province — higher thresholds due to climate):
  watch:     42°C
  warning:   46°C
  emergency: 49°C
  extreme:   52°C

HEAVY RAIN HOURLY (national):
  metric: precip_1h_mm
  watch:     15mm/hour
  warning:   25mm/hour
  emergency: 50mm/hour
  extreme:   75mm/hour

HEAVY RAIN 24H ACCUMULATION (national):
  metric: precip_24h_mm
  watch:     50mm/24h
  warning:   100mm/24h
  emergency: 150mm/24h
  extreme:   200mm/24h

WIND SPEED (national):
  metric: wind_gusts_kmh
  watch:     62 km/h  (tropical storm force)
  warning:   89 km/h  (category 1 cyclone)
  emergency: 119 km/h (category 2)
  extreme:   178 km/h (category 4+)

FLOOD GAUGE (national):
  metric: gauge_pct_of_danger
  watch:     60%  (at 60% of danger level)
  warning:   80%  (at 80% of danger level)
  emergency: 100% (at or above danger level)
  extreme:   120% (20% above danger level)

COLD WAVE (Gilgit-Baltistan province):
  metric: temp_min_c
  watch:     -5°C
  warning:   -10°C
  emergency: -15°C
  extreme:   -20°C
  direction: below  ← NOTE: below threshold, not above

SEVERE STORM (national):
  metric: cape_jkg
  watch:     1000 J/kg
  warning:   2500 J/kg
  emergency: 3500 J/kg
  extreme:   5000 J/kg
```

## 6.5 Duplicate Suppression

If the same location and same metric generates a breach repeatedly, only the first breach is dispatched. Subsequent identical breaches within the suppression window are marked as duplicates and suppressed.

```
SUPPRESSION WINDOWS BY METRIC TYPE:

Earthquake:    0 minutes  (each seismic event is unique by usgs_event_id)
Temperature:   180 minutes (3 hours — heatwave persists for hours)
Rainfall:      120 minutes (2 hours — rain event developing)
Wind:          60 minutes  (1 hour — storm passing through)
Flood gauge:   60 minutes  (1 hour — river level updating)

HOW SUPPRESSION WORKS:
  Before inserting new breach:
    Query: SELECT breach_id FROM threshold_breach_log
           WHERE (location matches) AND (metric matches)
           AND detected_at > (now - suppression_window)
    If row found: mark new breach as is_duplicate = TRUE
    If no row found: insert as new breach, dispatch

  Result: One dispatch per active disaster situation
  not hundreds of duplicate alerts
```

---

# PART 7: BREACH DISPATCH SYSTEM

---

## 7.1 How Dispatch Works

The threshold_breach_log table is the interface between the collection database and the main ClimaSync system. The dispatch service reads pending breach records and sends them to the main system's FastAPI endpoint.

```
┌──────────────────────────────────────────────────────────────────┐
│                    DISPATCH FLOW                                  │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Breach detected by collection service                        │
│     threshold_breach_log row created                             │
│     dispatch_status = 'pending'                                  │
│                                                                  │
│  2. Dispatch service runs every 30 seconds                       │
│     Reads undispatched_breaches view                             │
│     Gets pre-built dispatch_payload JSON                         │
│                                                                  │
│  3. HTTP POST to main system                                     │
│     URL: MAIN_SYSTEM_URL/alerts/incoming                         │
│     Header: X-API-Key: [internal key]                            │
│     Body: dispatch_payload JSON                                  │
│                                                                  │
│  4a. If POST succeeds (HTTP 200/201):                            │
│      Extract main_system_alert_id from response                  │
│      Update breach: dispatch_status = 'dispatched'              │
│      Update breach: main_system_alert_id = returned_id           │
│      Update breach: dispatched_at = now()                        │
│                                                                  │
│  4b. If POST fails:                                              │
│      Update breach: dispatch_status = 'dispatch_failed'         │
│      Increment: dispatch_attempt_count                           │
│      Store: last_dispatch_error = error message                  │
│      Will retry on next 30-second cycle                         │
│      After 5 failed attempts: no more retries                    │
│      Requires manual administrator intervention                  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

## 7.2 Dispatch Payload Structure

The dispatch payload sent to the main system contains everything needed to create an alert without the main system querying the collection database:

```
Dispatch payload contains:
  breach_id:           UUID of the breach record
  source_api:          which API detected this (usgs/open_meteo/etc)
  disaster_kind:       what type of disaster (earthquake/flood/etc)
  metric_name:         which metric triggered (magnitude/temp_max_c/etc)
  location_name:       human readable location name
  district:            Pakistan administrative district
  province:            Pakistan province enum value
  latitude:            decimal degrees
  longitude:           decimal degrees
  observed_value:      the actual measured value
  threshold_value:     the threshold that was crossed
  breach_severity:     watch/warning/emergency/extreme
  unit:                celsius/mm/richter/percent/etc
  observation_time:    when the measurement was taken (PKT)
  is_forecast:         boolean — is this a future prediction?
  forecast_horizon_h:  hours until forecasted breach (if is_forecast)
  detected_at:         when our system detected this (PKT)
```

---

# PART 8: COLLECTION CYCLE MANAGEMENT

---

## 8.1 What a Collection Cycle Is

Every time a collector runs (whether for USGS, Open-Meteo, or Flood Hub), it creates a collection cycle record. This record tracks everything about that run — how many locations were attempted, how many succeeded, how many rows were written, how many breaches were triggered, and how long it took.

## 8.2 Cycle Lifecycle

```
CYCLE LIFECYCLE:

1. CYCLE STARTS
   Collector calls cycle_repository.start_cycle()
   New row in collection_cycles with status = 'running'
   cycle_id returned and tracked throughout the run

2. CYCLE EXECUTES
   For each API call: update running counters
   locations_targeted increments for each attempted location
   locations_success increments for each successful call
   locations_failed increments for each error
   rows_upserted increments for each existing row updated
   rows_inserted increments for each new row created
   breaches_triggered increments for each breach detected

3. CYCLE COMPLETES
   Collector calls cycle_repository.complete_cycle()
   status updated to: completed / partial / failed
   completed_at timestamp set
   duration_ms calculated
   avg_latency_ms calculated
   error_summary populated with any failed location details

4. API HEALTH UPDATED
   sync_api_health_on_cycle trigger fires automatically
   api_registry updated with latest health state
   consecutive_failures updated
   avg_latency_ms rolling average updated
```

## 8.3 Cycle Status Meanings

```
completed:  All targeted locations successfully polled
partial:    Some locations succeeded, some failed
            System continues — partial data is better than none
failed:     No locations succeeded, entire cycle failed
            Consecutive_failures increments
            After 3+ failed cycles: api_health_state → 'down'
skipped:    Cycle was due but skipped because:
            - API is currently in backoff period
            - Previous cycle still running (max_instances=1)
            - Manual skip via admin interface
```

---

# PART 9: SCHEDULER CONFIGURATION

---

## 9.1 All Scheduled Jobs

The APScheduler runs all data collection and maintenance jobs:

```
┌──────────────────────────────────────────────────────────────────┐
│                    SCHEDULER JOBS                                │
├────────────────────────┬──────────────┬───────────────────────   │
│  JOB NAME              │  INTERVAL    │  WHAT IT DOES           │
├────────────────────────┼──────────────┼───────────────────────   │
│  usgs_collection       │  5 minutes   │  Polls USGS for new     │
│                        │              │  Pakistan earthquakes    │
├────────────────────────┼──────────────┼───────────────────────   │
│  weather_collection    │  2 hours     │  Checks which locations │
│                        │  (check)     │  are due for polling    │
│                        │  3-6h (poll) │  Polls those that are   │
├────────────────────────┼──────────────┼───────────────────────   │
│  flood_current         │  1 hour      │  Gets current river     │
│                        │              │  gauge readings         │
├────────────────────────┼──────────────┼───────────────────────   │
│  flood_forecasts       │  6 hours     │  Gets 5-day flood       │
│                        │              │  forecast per gauge     │
├────────────────────────┼──────────────┼───────────────────────   │
│  breach_dispatch       │  30 seconds  │  Sends pending breaches │
│                        │              │  to main system         │
├────────────────────────┼──────────────┼───────────────────────   │
│  threshold_reload      │  1 hour      │  Refreshes threshold    │
│                        │              │  cache from database    │
├────────────────────────┼──────────────┼───────────────────────   │
│  daily_cleanup         │  00:05 PKT   │  Deletes expired rows   │
│                        │  daily       │  from all window tables │
└────────────────────────┴──────────────┴───────────────────────   │
```

## 9.2 Job Safety Rules

```
All jobs follow these safety rules:

max_instances = 1
  A job cannot run concurrently with itself
  If USGS poll takes 70 seconds, the next 5-minute
  trigger fires but is dropped, not queued

coalesce = True
  If a job misses multiple triggers (server was down),
  it runs only once when it comes back, not multiple times

error isolation:
  Each job is wrapped in try/except
  A failed job logs the error but does not crash the scheduler
  Other jobs continue running normally

misfire_grace_time = 30 seconds
  If a job trigger misfires by less than 30 seconds,
  it still runs. If more than 30 seconds late, it is skipped.
```

## 9.3 Daily Cleanup Logic

The cleanup function runs at 00:05 PKT every night:

```
TABLES CLEANED AND CRITERIA:

weather_hourly_window:
  DELETE WHERE forecast_date < CURRENT_DATE (Pakistan date)
  → Removes yesterday's hourly data
  → Rows for today through day 4 remain

weather_daily_summaries:
  DELETE WHERE summary_date < CURRENT_DATE
  → Removes yesterday's daily summary

seismic_events:
  DELETE WHERE DATE(earthquake_time AT TIME ZONE 'Asia/Karachi')
               < CURRENT_DATE - INTERVAL '4 days'
  → Removes earthquakes older than 5 days Pakistan time

flood_gauge_forecasts:
  DELETE WHERE forecast_date < CURRENT_DATE
  → Removes past forecast hours

threshold_breach_log:
  DELETE WHERE detected_at < now() - INTERVAL '5 days'
               AND dispatch_status = 'dispatched'
  → Removes old dispatched (processed) breach records
  → Keeps undispatched records regardless of age

TABLES NOT CLEANED (permanent reference data):
  api_registry, pakistan_locations, pakistan_infrastructure,
  disaster_thresholds, flood_gauge_registry,
  flood_gauge_current (always exactly one row per gauge)
```

---

# PART 10: MONITORING LOCATIONS

---

## 10.1 Pakistan Coverage Strategy

For the prototype, 15 strategically chosen locations provide complete geographic and risk-type coverage across Pakistan:

```
┌──────────────────────────────────────────────────────────────────┐
│              PROTOTYPE MONITORING LOCATIONS (15)                 │
├─────────────────────┬────────────────┬────────────┬─────────────┤
│  LOCATION           │  PROVINCE      │  PRIORITY  │  RISK FOCUS │
├─────────────────────┼────────────────┼────────────┼─────────────┤
│  TIER 1 — PROVINCIAL CAPITALS (5)                               │
├─────────────────────┼────────────────┼────────────┼─────────────┤
│  Karachi            │  Sindh         │  Critical  │  Heat, Flood│
│  Lahore             │  Punjab        │  Critical  │  Rain, Heat │
│  Islamabad          │  ICT           │  Critical  │  Seismic    │
│  Peshawar           │  KPK           │  Critical  │  Seismic    │
│  Quetta             │  Balochistan   │  Critical  │  Seismic    │
├─────────────────────┼────────────────┼────────────┼─────────────┤
│  TIER 2 — MAJOR CITIES (7)                                      │
├─────────────────────┼────────────────┼────────────┼─────────────┤
│  Multan             │  Punjab        │  High      │  Heat, Rain │
│  Faisalabad         │  Punjab        │  High      │  Rain, Heat │
│  Hyderabad          │  Sindh         │  High      │  Heat, Flood│
│  Sukkur             │  Sindh         │  High      │  Flood      │
│  Gilgit             │  GB            │  High      │  Seismic    │
│  Muzaffarabad       │  AJK           │  High      │  Seismic    │
│  Abbottabad         │  KPK           │  High      │  Seismic    │
├─────────────────────┼────────────────┼────────────┼─────────────┤
│  TIER 3 — DISASTER ZONES (3)                                    │
├─────────────────────┼────────────────┼────────────┼─────────────┤
│  Larkana            │  Sindh         │  Medium    │  Flood      │
│  Dera Ghazi Khan    │  Punjab        │  Medium    │  Flood      │
│  Chaman             │  Balochistan   │  Medium    │  Seismic    │
└─────────────────────┴────────────────┴────────────┴─────────────┘
```

## 10.2 Location Data Stored

For each location, the following vulnerability context is stored and used by the Risk Analysis Agent:

```
Geographic data:
  coordinates, elevation, area_sq_km

Population data:
  population (from PBS census)
  population_density (per sq km)
  urban_population_pct

Risk profile:
  flood_risk_zone (zone_1_low through zone_5_critical)
  seismic_zone (I through IV)
  heat_risk_zone
  drought_risk_zone

Infrastructure quality:
  infrastructure_quality (very_low through critical)
  drainage_quality (determines flood impact)
  building_stock (kutcha/semi_pucca/pucca/mixed)
  hospital_count, school_count
```

---

# PART 11: API HEALTH MANAGEMENT

---

## 11.1 API Health State Machine

Each API transitions through health states based on call outcomes:

```
                    ┌──────────┐
                    │ unknown  │ ← Initial state at startup
                    └────┬─────┘
                         │ First successful call
                         ↓
    ┌────────────────────────────────────────┐
    │              healthy                   │ ← All calls succeeding
    └──┬─────────────────────────────────────┘
       │ 1-2 failures        │ HTTP 429
       ↓                     ↓
  ┌─────────┐         ┌──────────────┐
  │degraded │         │ rate_limited │ ← In backoff period
  └────┬────┘         └──────┬───────┘
       │ 3+ failures          │ Backoff expires, next call fails
       ↓                      ↓
  ┌─────────┐
  │  down   │ ← 3+ consecutive failures, likely API outage
  └────┬────┘
       │ Successful call
       ↓
  ┌─────────┐
  │ healthy │ ← Recovered, failures reset to 0
  └─────────┘
```

## 11.2 Exponential Backoff Formula

When rate limited or after failures:

```
backoff_duration = min(
  initial_backoff_s × (backoff_multiplier ^ consecutive_failures),
  max_backoff_s
)

With defaults (initial=10s, multiplier=2.0, max=600s):
  Attempt 1: 10s
  Attempt 2: 20s
  Attempt 3: 40s
  Attempt 4: 80s
  Attempt 5: 160s
  Attempt 6: 320s
  Attempt 7: 600s (capped at maximum)
  All subsequent: 600s
```

## 11.3 Rate Limit State Persistence

The api_registry table persists rate limit state across server restarts:

```
PROBLEM WITHOUT PERSISTENCE:
  Service hits Open-Meteo rate limit at 14:30
  Server restarts at 14:35
  Service immediately calls Open-Meteo at startup
  Gets blocked again with 429
  Causes API account to be flagged

SOLUTION WITH PERSISTENCE:
  Service hits Open-Meteo rate limit at 14:30
  api_registry.backoff_until = 14:45 (saved to DB)
  Server restarts at 14:35
  Service reads api_registry at startup
  Sees backoff_until = 14:45
  Waits until 14:45 before first call
  Rate limit respected across restart
```

---

# PART 12: HTTP API ENDPOINTS

---

## 12.1 Available Endpoints

The Data Collection Service exposes these HTTP endpoints for monitoring and administration:

```
┌──────────────────────────────────────────────────────────────────┐
│                    EXPOSED HTTP ENDPOINTS                        │
├─────────────┬────────────────────────────────────────────────────┤
│  METHOD/URL │  DESCRIPTION                                       │
├─────────────┼────────────────────────────────────────────────────┤
│  GET        │  Basic health check                                │
│  /health    │  Returns: status, database connectivity,           │
│             │  uptime_seconds, timestamp (PKT)                   │
├─────────────┼────────────────────────────────────────────────────┤
│  GET        │  Per-API health status                             │
│  /health    │  Returns for each API:                             │
│  /apis      │  health_state, last_success_at,                   │
│             │  consecutive_failures, is_in_backoff,              │
│             │  backoff_remaining_seconds                         │
├─────────────┼────────────────────────────────────────────────────┤
│  GET        │  Recent collection cycle history                   │
│  /status    │  Returns last 10 cycles per API:                  │
│  /cycles    │  status, duration, success_rate, breaches          │
├─────────────┼────────────────────────────────────────────────────┤
│  GET        │  Breach dispatch statistics                        │
│  /status    │  Returns: pending_count, dispatched_today,         │
│  /breaches  │  failed_count, last_breach_at                      │
├─────────────┼────────────────────────────────────────────────────┤
│  GET        │  Location poll state overview                      │
│  /status    │  Returns per location:                             │
│  /locations │  last_polled_at, next_poll_due_at,                 │
│             │  consecutive_failures, last_poll_outcome           │
└─────────────┴────────────────────────────────────────────────────┘
```

## 12.2 API Security

All endpoints are protected by API key authentication:

```
Header required: X-API-Key: [configured internal key]

If missing or wrong: HTTP 403 Forbidden returned
The key is set in .env as MAIN_SYSTEM_API_KEY
Only the main ClimaSync backend and admin tools know this key
```

---

# PART 13: APPLICATION STARTUP AND SHUTDOWN

---

## 13.1 Startup Sequence

When the service starts, it executes these steps in order:

```
STARTUP SEQUENCE:

Step 1: Load configuration
  Read all .env variables via config.py
  Validate all required values are present
  If any required value missing: refuse to start

Step 2: Initialize logger
  Set log level from config
  Configure log format with timestamps in PKT

Step 3: Connect to database
  Create asyncpg connection pool
  Min 2 connections, max 10 connections
  SET timezone = 'Asia/Karachi' on each connection
  Test with: SELECT 1
  If connection fails: refuse to start

Step 4: Load reference data into memory
  Load all active pakistan_locations
  Load all active disaster_thresholds
  Load all api_registry rows
  Load all active flood_gauge_registry rows
  Store in InMemoryCache object shared across app
  If any load fails: log error but continue
  (service can still run with partial data)

Step 5: Initialize all components
  Create CollectionDatabase pool
  Create BaseCollector HTTP client (shared httpx.AsyncClient)
  Create UsgsCollector with references to service + repository
  Create OpenMeteoCollector with references
  Create FloodHubCollector with references
  Create BreachService with loaded thresholds
  Create DispatchService with HTTP client

Step 6: Initialize and start APScheduler
  Create AsyncIOScheduler
  Register all 7 jobs with their intervals
  Start scheduler
  First job runs immediately after start for USGS
  Other jobs wait for their first trigger

Step 7: Log startup complete
  "ClimaSync Collection Service started"
  "Monitoring X locations across Pakistan"
  "X active flood gauges registered"
  "X disaster thresholds loaded"
  "All schedulers running"
  Total startup time logged

TOTAL STARTUP TIME: Target under 5 seconds
```

## 13.2 Shutdown Sequence

When the service receives a shutdown signal (SIGTERM or CTRL+C):

```
SHUTDOWN SEQUENCE:

Step 1: Stop accepting new HTTP requests
  FastAPI stops accepting connections

Step 2: Stop scheduler gracefully
  No new jobs are triggered
  Currently running jobs are allowed to complete
  Wait up to 30 seconds for running jobs to finish
  After 30 seconds: force stop

Step 3: Close HTTP client
  httpx.AsyncClient closes all connections

Step 4: Close database pool
  All connections returned to pool
  Pool closes all connections
  No data loss — all writes committed before shutdown

Step 5: Log shutdown complete
  "ClimaSync Collection Service stopped gracefully"
  Total uptime logged
```

---

# PART 14: ERROR HANDLING STRATEGY

---

## 14.1 Error Categories and Responses

```
┌──────────────────────────────────────────────────────────────────┐
│                    ERROR HANDLING MATRIX                         │
├─────────────────────┬──────────────────────────────────────────  │
│  ERROR TYPE         │  HOW HANDLED                               │
├─────────────────────┼──────────────────────────────────────────  │
│  API 429            │  Enter backoff, skip until backoff expires  │
│  Rate Limited       │  Log event, update api_registry            │
│                     │  Other collectors continue normally         │
├─────────────────────┼──────────────────────────────────────────  │
│  API Timeout        │  Retry with tenacity (3 attempts)           │
│                     │  If all fail: mark location as failed       │
│                     │  Update consecutive_failures                │
│                     │  Continue to next location                 │
├─────────────────────┼──────────────────────────────────────────  │
│  API Down           │  Log error, mark cycle as partial/failed    │
│                     │  After 3 cycles: api_health → 'down'        │
│                     │  Continue attempting every cycle            │
│                     │  Alert admin via health endpoint            │
├─────────────────────┼──────────────────────────────────────────  │
│  Invalid Response   │  Log raw response for debugging             │
│                     │  Skip this location this cycle              │
│                     │  Do NOT crash the collector                 │
├─────────────────────┼──────────────────────────────────────────  │
│  Database Error     │  Retry 3 times with 1 second delay          │
│                     │  If all fail: log error, continue           │
│                     │  Data from that location is skipped         │
│                     │  Next cycle will retry                      │
├─────────────────────┼──────────────────────────────────────────  │
│  Dispatch Failure   │  Mark breach as dispatch_failed             │
│                     │  Retry on next 30-second cycle              │
│                     │  After 5 attempts: stop retrying            │
│                     │  Require manual admin intervention          │
├─────────────────────┼──────────────────────────────────────────  │
│  Scheduler Job      │  Log full error with stack trace            │
│  Exception          │  Job is marked as failed                    │
│                     │  Scheduler continues all other jobs         │
│                     │  Failed job will retry on next trigger      │
└─────────────────────┴──────────────────────────────────────────  │
```

## 14.2 The Fundamental Resilience Rule

```
A single failure in one component must never stop the rest.

If USGS is down:
  → Weather collection continues normally
  → Flood collection continues normally
  → Previously detected breaches continue dispatching

If Open-Meteo is rate limited:
  → USGS collection continues normally
  → Flood collection continues normally
  → Weather data from last successful poll remains in DB

If dispatch to main system fails:
  → All collection continues normally
  → Breach records remain in threshold_breach_log
  → Dispatch retries automatically
  → No data is lost
```

---

# PART 15: DATA FLOW — END TO END

---

## 15.1 Complete Flow: Earthquake Detection

```
T+0:00  Earthquake M6.2 occurs near Muzaffarabad

T+2:30  USGS detects and publishes to their feed

T+3:00  (at most) Our USGS collector runs (5m interval)
         Calls USGS API with Pakistan bounding box
         New feature found in GeoJSON response
         Parse: magnitude=6.2, depth=12km (shallow), place="Muzaffarabad area"
         Resolve: nearest location → Muzaffarabad (pakistan_locations)
         Compute: magnitude_class=strong (trigger fires)
         Compute: depth_class=shallow (trigger fires)
         UPSERT into seismic_events (new row, usgs_event_id is unique)

T+3:01  Breach check runs
         find_threshold: magnitude, earthquake, azad_kashmir province
         Finds national default: warning=5.0, emergency=6.0
         6.2 > 6.0 → emergency threshold crossed
         check_duplicate: no recent earthquake breach for this event
         INSERT into threshold_breach_log
         dispatch_status = 'pending'
         breach_severity = 'emergency'

T+3:30  (at most) Dispatch service runs (30s interval)
         Reads undispatched_breaches view
         Gets pre-built dispatch_payload for this breach
         POST to main system /alerts/incoming
         Main system creates alert record
         Returns new alert_id
         Update threshold_breach_log:
           dispatch_status = 'dispatched'
           main_system_alert_id = returned UUID

T+3:31  Main system Verification Agent activates
         (This is outside scope of this document)

T+4:00  USGS updates the event (magnitude refined to 6.4)
         Next USGS cycle detects same usgs_event_id with updated data
         UPSERT: updates magnitude to 6.4
         track_magnitude_revision trigger fires
         initial_magnitude saved as 6.2, magnitude_was_revised = TRUE
         Breach already dispatched — no second dispatch for same event
```

## 15.2 Complete Flow: Heatwave Detection (Proactive)

```
Today is 15 July 2025, 09:00 PKT

Open-Meteo collector runs for Karachi:
  Fetches 5-day forecast
  Parses all 120 hours
  For 18 July 14:00 (day 3, hour 78):
    temp_max_c = 48.5°C
    This is forecast data (is_forecast = TRUE)
    UPSERT into weather_hourly_window for this future hour

Breach check for that future hour:
  find_threshold: temp_max_c, heatwave, sindh province
  Sindh threshold: emergency=49°C, warning=46°C
  48.5 > 46 but < 49 → warning threshold crossed
  is_forecast_breach = TRUE
  forecast_horizon_h = 77 (hours until 18 July 14:00)

INSERT into threshold_breach_log:
  is_forecast_breach = TRUE
  forecast_horizon_h = 77
  breach_severity = warning
  observed_value = 48.5
  threshold_value = 46.0

Dispatch to main system:
  Verification Agent receives this 77 HOURS in advance
  Risk Analysis Agent can assess heat impact on Karachi's 16M people
  NGOs can pre-position medical teams and water distribution
  Social media posts can warn public 3 days ahead
  This is the PRE-ACTIVE capability
```

## 15.3 Complete Flow: Flood Warning (Predictive)

```
Current: Jhelum River at Mangla gauge is at 65% of danger level

Flood Hub collector runs:
  Get current reading: level=7.2m, danger=11.0m
  Previous reading: 6.8m (30 minutes ago)
  level_change = 7.2 - 6.8 = +0.4m in 30 minutes
  rise_rate = 0.4m / 0.5h = 0.8 m/h
  river_trend = rapidly_rising
  hours_to_danger = (11.0 - 7.2) / 0.8 = 4.75 hours
  pct_of_danger = (7.2/11.0) × 100 = 65.5%

Breach check (current):
  gauge_pct_of_danger = 65.5 > 60% watch threshold
  → watch breach created and dispatched

Flood forecasts collected:
  36-hour forecast: level_p90 = 11.8m (above danger)
  prob_exceeds_danger = 35%

Breach check (forecast):
  35% probability of danger in 36 hours
  Forecast breach created: emergency level
  is_forecast_breach = TRUE, forecast_horizon_h = 36

Both breaches dispatched to main system:
  Verification Agent sees current watch + upcoming 35% danger probability
  Risk Analysis Agent estimates downstream affected population
  Precaution Definer prepares evacuation plan for Mangla downstream areas
  Task Allocator pre-positions boats along Jhelum river towns
  36 hours before the flood peak
```

---

# PART 16: CONFIGURATION REFERENCE

---

## 16.1 All Environment Variables

```
┌──────────────────────────────────────────────────────────────────┐
│              COMPLETE ENVIRONMENT VARIABLE REFERENCE             │
├──────────────────────────────────┬───────────────────────────────┤
│  VARIABLE                        │  PURPOSE / DEFAULT            │
├──────────────────────────────────┼───────────────────────────────┤
│  DATABASE                        │                               │
│  COLLECTION_DB_HOST              │  Supabase DB hostname         │
│  COLLECTION_DB_PORT              │  5432 (PostgreSQL default)    │
│  COLLECTION_DB_NAME              │  postgres                     │
│  COLLECTION_DB_USER              │  postgres                     │
│  COLLECTION_DB_PASSWORD          │  Your Supabase DB password    │
│  COLLECTION_DB_POOL_MIN          │  2 (minimum pool connections) │
│  COLLECTION_DB_POOL_MAX          │  10 (maximum pool connections)│
├──────────────────────────────────┼───────────────────────────────┤
│  MAIN SYSTEM CONNECTION          │                               │
│  MAIN_SYSTEM_BASE_URL            │  http://localhost:8001        │
│  MAIN_SYSTEM_API_KEY             │  Internal auth key            │
├──────────────────────────────────┼───────────────────────────────┤
│  USGS SETTINGS                   │                               │
│  USGS_BASE_URL                   │  USGS API endpoint            │
│  USGS_MIN_MAGNITUDE              │  2.5 (minimum to capture)     │
│  USGS_LOOKBACK_HOURS             │  6 (overlap for updates)      │
│  USGS_POLL_INTERVAL_SECONDS      │  300 (every 5 minutes)        │
├──────────────────────────────────┼───────────────────────────────┤
│  OPEN-METEO SETTINGS             │                               │
│  OPENMETEO_BASE_URL              │  Open-Meteo API endpoint      │
│  OPENMETEO_POLL_INTERVAL_MINUTES │  120 (scheduler check)        │
│  OPENMETEO_REQUEST_DELAY_MS      │  500 (between locations)      │
├──────────────────────────────────┼───────────────────────────────┤
│  GOOGLE FLOOD HUB SETTINGS       │                               │
│  GOOGLE_FLOOD_HUB_BASE_URL       │  Flood Hub endpoint           │
│  GOOGLE_FLOOD_HUB_API_KEY        │  Your Google Cloud key        │
├──────────────────────────────────┼───────────────────────────────┤
│  PAKISTAN BOUNDS (do not change) │                               │
│  PAKISTAN_MIN_LAT                │  23.0                         │
│  PAKISTAN_MAX_LAT                │  38.0                         │
│  PAKISTAN_MIN_LON                │  60.0                         │
│  PAKISTAN_MAX_LON                │  78.0                         │
├──────────────────────────────────┼───────────────────────────────┤
│  SCHEDULER INTERVALS             │                               │
│  FLOOD_CURRENT_INTERVAL_MINUTES  │  60                           │
│  FLOOD_FORECAST_INTERVAL_HOURS   │  6                            │
│  BREACH_DISPATCH_INTERVAL_SECS   │  30                           │
│  THRESHOLD_RELOAD_INTERVAL_HRS   │  1                            │
│  CLEANUP_HOUR_PKT                │  0 (midnight)                 │
│  CLEANUP_MINUTE_PKT              │  5 (00:05 PKT)                │
├──────────────────────────────────┼───────────────────────────────┤
│  DISPATCH SETTINGS               │                               │
│  MAX_DISPATCH_ATTEMPTS           │  5                            │
│  DISPATCH_BATCH_SIZE             │  10 (per 30s cycle)           │
├──────────────────────────────────┼───────────────────────────────┤
│  APPLICATION                     │                               │
│  APP_PORT                        │  8000                         │
│  APP_ENV                         │  development / production     │
│  LOG_LEVEL                       │  INFO / DEBUG / WARNING       │
│  SERVICE_NAME                    │  climasync-collection         │
└──────────────────────────────────┴───────────────────────────────┘
```

---

# PART 17: TESTING STRATEGY

---

## 17.1 Test Categories

```
UNIT TESTS (test each component in isolation):

  test_usgs_collector.py
    → USGS GeoJSON response parsed correctly
    → Pakistan bounding box filtering works
    → Magnitude classification correct
    → UPSERT does not create duplicate rows
    → Expired events cleaned up correctly

  test_weather_collector.py
    → Open-Meteo response parsed correctly
    → WMO code 65 → heavy_rain (trigger verification)
    → Wind direction 225° → SW (trigger verification)
    → Day offset computed correctly for each date
    → Rolling precipitation sums computed correctly
    → 5-day window enforced (day 5+ rejected)
    → UPSERT does not create duplicates

  test_flood_collector.py
    → Gauge current reading parsed correctly
    → Rise rate computed from previous reading
    → River trend classified correctly
    → hours_to_danger projection correct
    → Probabilistic forecast parsed correctly
    → p10/p50/p90 stored separately

  test_breach_detection.py
    → Correct threshold selected (district beats province beats national)
    → Breach level assigned correctly (watch/warning/emergency/extreme)
    → above direction: value above threshold triggers breach
    → below direction: value below threshold triggers breach
    → Duplicate suppression within window works
    → Duplicate suppression respects window boundary exactly
    → Season detection correct (July → monsoon)

INTEGRATION TESTS (test components together):
  → USGS collector end-to-end with real API call
  → Weather collector end-to-end for one location
  → Breach detection with real threshold data from DB
  → Dispatch service sends to mock main system endpoint

VERIFICATION TESTS (database verification):
  → After USGS run: seismic_events has correct rows
  → After weather run: 120 rows per location
  → After second weather run: still 120 rows (UPSERT)
  → Triggers fired: magnitude_class set, depth_class set
  → Views return data: significant_recent_earthquakes query works
```

---

# PART 18: IMPLEMENTATION SUMMARY

---

## 18.1 Development Order

```
BUILD IN THIS EXACT ORDER:

1.  core/config.py          ← Everything reads from here first
2.  core/logger.py          ← Everything logs through here
3.  core/exceptions.py      ← Custom exception types
4.  core/security.py        ← API key protection
5.  database/connection.py  ← Database pool
6.  database/queries/       ← All SQL strings
7.  models/                 ← All Pydantic schemas
8.  repositories/           ← Database operations
9.  services/breach_service.py ← Threshold logic (used by all)
10. collectors/base_collector.py ← HTTP client (used by all)
11. collectors/usgs_collector.py + services/usgs_service.py
12. api/routes/health_controller.py + status_controller.py
13. main.py                 ← Wire everything together
    → Test USGS end-to-end here before continuing
14. collectors/openmeteo + services/openmeteo_service.py
    → Test weather end-to-end here
15. collectors/floodhub + services/floodhub_service.py
    → Test flood end-to-end here
16. services/dispatch_service.py
17. scheduler/job_scheduler.py
    → Final integration test with all components
```

## 18.2 Success Criteria

The Data Collection Service is complete and working when:

```
✅ Service starts without errors and health endpoint returns healthy
✅ USGS collector runs every 5 minutes
   → seismic_events table has Pakistan earthquake data
   → magnitude_class and depth_class set by triggers
   → Running twice does not duplicate rows

✅ Open-Meteo collector runs for all 15 locations
   → weather_hourly_window has 120 rows per location
   → weather_daily_summaries has 5 rows per location
   → weather_condition set by WMO decode trigger
   → Running twice does not duplicate rows
   → Rate limiting with 500ms delay works

✅ Google Flood Hub collector runs for all active gauges
   → flood_gauge_current has one row per gauge (overwritten)
   → flood_gauge_forecasts has forecast data per gauge
   → Rise rate and river trend computed correctly

✅ Breach detection works for all metric types
   → Pakistan-specific thresholds applied
   → Duplicate suppression prevents repeated alerts
   → Forecast breaches detected in advance

✅ Dispatch service sends breaches to main system
   → threshold_breach_log shows dispatched status
   → Retry logic works for failed dispatches

✅ Rolling window cleanup runs at midnight PKT
   → Expired rows deleted from time-series tables
   → Fixed row count maintained

✅ All health endpoints return accurate information
✅ Service recovers from API failures without crashing
✅ Service runs continuously for 24 hours without intervention
```

---

```
╔══════════════════════════════════════════════════════════════════════╗
║                     DOCUMENT COMPLETE                                ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  Document:    ClimaSync.ai Data Collection Service                   ║
║  Coverage:    Complete technical reference                           ║
║  Parts:       18 parts covering all aspects                         ║
║                                                                      ║
║  SECTIONS COVERED:                                                   ║
║  ✅ Project context and agent architecture                           ║
║  ✅ Service overview and purpose                                     ║
║  ✅ Technology stack with justification                              ║
║  ✅ Layered architecture pattern                                     ║
║  ✅ Complete file structure                                          ║
║  ✅ Database design (12 tables, 17 enums, 10 triggers, 8 views)     ║
║  ✅ USGS API integration (parameters, response, refinement)         ║
║  ✅ Open-Meteo API integration (all variables, CAPE, WMO codes)     ║
║  ✅ Google Flood Hub integration (current + probabilistic forecast)  ║
║  ✅ Threshold breach detection with Pakistan-specific values         ║
║  ✅ Duplicate suppression logic                                      ║
║  ✅ Breach dispatch system with retry logic                         ║
║  ✅ Collection cycle management                                      ║
║  ✅ Scheduler configuration (all 7 jobs)                            ║
║  ✅ 15 prototype monitoring locations                               ║
║  ✅ API health state machine and exponential backoff                 ║
║  ✅ HTTP endpoints for monitoring                                    ║
║  ✅ Startup and shutdown sequences                                   ║
║  ✅ Error handling matrix                                            ║
║  ✅ Three complete end-to-end data flow examples                    ║
║  ✅ All environment variables documented                             ║
║  ✅ Testing strategy                                                 ║
║  ✅ Build order and success criteria                                 ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
```