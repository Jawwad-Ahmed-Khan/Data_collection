<div align="center">

# ClimaSync — Data Collection Service

**Real-time disaster monitoring for Pakistan** · Earthquakes · Floods · Extreme Weather

[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.135-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![asyncpg](https://img.shields.io/badge/asyncpg-0.31-336791?style=flat-square&logo=postgresql&logoColor=white)](https://magicstack.github.io/asyncpg/)
[![APScheduler](https://img.shields.io/badge/APScheduler-3.11-FF6B6B?style=flat-square)](https://apscheduler.readthedocs.io/)
[![Supabase](https://img.shields.io/badge/Database-Supabase-3ECF8E?style=flat-square&logo=supabase&logoColor=white)](https://supabase.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)

<br/>

> Part of the **ClimaSync.ai** platform — an AI-powered early warning system built for Pakistan's disaster management authorities.

</div>

---

## Table of Contents

- [Overview](#-overview)
- [Features](#-features)
- [Architecture](#-architecture)
- [External APIs](#-external-apis)
- [Breach Detection](#-breach-detection)
- [Scheduled Jobs](#-scheduled-jobs)
- [API Endpoints](#-api-endpoints)
- [Project Structure](#-project-structure)
- [Getting Started](#-getting-started)
- [Environment Variables](#-environment-variables)
- [Database Schema](#-database-schema)
- [Running Tests](#-running-tests)
- [Tech Stack](#-tech-stack)

---

## 🌐 Overview

The **ClimaSync Data Collection Service** is a standalone Python microservice that continuously monitors Pakistan for disaster conditions. It runs 24/7, polling three external APIs on configurable schedules, comparing measurements against regional disaster thresholds, and dispatching breach alerts to the main ClimaSync platform.

**Geographic scope:** Pakistan bounding box — 23°N–38°N, 60°E–78°E  
**Timezone:** All timestamps stored and processed in **PKT (Asia/Karachi)**  
**Database:** Supabase (PostgreSQL) via asyncpg connection pool

---

## ✨ Features

| Feature | Detail |
|---|---|
| 🌍 **Multi-source collection** | USGS Earthquakes · Open-Meteo Weather · Google Flood Hub |
| ⚡ **Real-time scheduling** | 7 APScheduler jobs firing from every 30 seconds to daily |
| 🚨 **Smart breach detection** | District → Province → National threshold priority, season-aware |
| 🔁 **Retry & backoff** | Tenacity (3 attempts, exponential backoff) + HTTP 429 backoff stored in DB |
| 🛡️ **Error isolation** | One job failure never affects other running jobs |
| 📦 **In-memory cache** | Thresholds and locations pre-loaded at startup, reloaded hourly |
| 📤 **Breach dispatch** | Automatic retry of failed alerts to main system (up to 5 attempts) |
| 🧹 **Rolling cleanup** | Daily cron deletes expired data (seismic: 30d, weather: 7-14d, flood: 7d) |
| 🔒 **API key auth** | All HTTP endpoints protected with constant-time `X-API-Key` validation |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                  ClimaSync Data Collection Service                       │
│                                                                          │
│  ┌─────────────┐  ┌─────────────────┐  ┌──────────────────────────┐    │
│  │ COLLECTORS  │  │    SERVICES     │  │     SCHEDULER            │    │
│  │             │  │                 │  │                          │    │
│  │ USGS ──────►│  │ USGSService     │  │  Job 1: USGS     (60s)   │    │
│  │ OpenMeteo ─►│  │ OpenMeteoService│  │  Job 2: Weather (15min)  │    │
│  │ FloodHub ──►│  │ FloodHubService │  │  Job 3: Flood   (30min)  │    │
│  │             │  │                 │  │  Job 4: Forecast  (6h)   │    │
│  │  (inherit   │  │ BreachService ◄─┼──┼──────────────────────    │    │
│  │   from      │  │  (shared by    │  │  Job 5: Dispatch (30s)   │    │
│  │   Base)     │  │   all 3)       │  │  Job 6: Reload    (1h)   │    │
│  │             │  │                 │  │  Job 7: Cleanup  (daily) │    │
│  │             │  │ DispatchService │  │                          │    │
│  └─────────────┘  └─────────────────┘  └──────────────────────────┘    │
│          │                │                         │                    │
│          ▼                ▼                         ▼                    │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                    REPOSITORIES + DATABASE POOL                   │  │
│  │   SeismicRepo · WeatherRepo · FloodRepo · BreachRepo · CycleRepo  │  │
│  │              asyncpg → Supabase PostgreSQL (SSL)                  │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
          │                                             │
          ▼                                             ▼
   External APIs:                            Main ClimaSync System
   • USGS Earthquake API                     POST /alerts/incoming
   • Open-Meteo Forecast API                 (breach dispatch)
   • Google Flood Hub API
```

### Startup Sequence (7 Steps)

```
1. Load & validate all .env variables (fail fast if missing)
2. Initialize structured JSON logger (PKT timestamps)
3. Connect asyncpg pool to Supabase + test with SELECT 1
4. Load reference data into InMemoryCache
   ├── 15 Pakistan monitoring locations
   ├── 21 disaster thresholds
   ├── 3 API configurations
   └── 10 flood gauge registrations
5. Initialize all components
   ├── Shared httpx.AsyncClient
   ├── All Repositories
   ├── All Services (including shared BreachService)
   └── All Collectors
6. Start APScheduler with all 7 jobs
7. Register API routes (/health, /status) → Service READY
```

---

## 🌐 External APIs

### 1. USGS Earthquake API
- **URL:** `https://earthquake.usgs.gov/fdsnws/event/1/query`
- **Auth:** None (free, public)
- **Schedule:** Every **60 seconds**
- **Query:** GeoJSON format, Pakistan bounding box, min magnitude 2.5, last 6-hour window
- **Stores:** `seismic_events` table (UPSERT by `usgs_event_id`, 30-day rolling window)

### 2. Open-Meteo Forecast API
- **URL:** `https://api.open-meteo.com/v1/forecast`
- **Auth:** None (free tier)
- **Schedule:** Every **15 minutes** per location
- **Query:** Hourly variables (temperature, precipitation, wind, humidity) + daily summaries for each of 15 Pakistan locations
- **Stores:** `weather_hourly_window` (7-day rolling), `weather_daily_summary` (14-day rolling)

### 3. Google Flood Hub API
- **URL:** `https://floodhub.googleapis.com/v1`
- **Auth:** Google Cloud API Key (`Authorization: Bearer`)
- **Schedules:**
  - Current water levels: every **30 minutes**
  - Probabilistic forecasts (p10/p50/p90): every **6 hours**
- **Monitors:** 10 registered river gauges across Pakistan
- **Derived metrics:** Rise rate (m/hr), trend (rising/steady/falling), time-to-danger

---

## 🚨 Breach Detection

The `BreachService` is the heart of the system — used by all three collectors.

### Threshold Priority Lookup

When a reading is checked, the most specific applicable threshold wins:

```
Priority (highest → lowest):
  1. District match + Season match    (score: 110)
  2. District match + Year-round      (score: 100)
  3. Province match + Season match    (score:  60)
  4. Province match + Year-round      (score:  50)
  5. National + Season match          (score:  10)
  6. National + Year-round            (score:   0)
```

### Severity Levels

| Level | Description |
|---|---|
| `watch` | Conditions approaching dangerous range |
| `warning` | Dangerous conditions present |
| `emergency` | Serious immediate threat |
| `extreme` | Catastrophic conditions |

### Pakistan Seasons

| Season | Months |
|---|---|
| `monsoon` | July – September |
| `pre_monsoon` | April – June |
| `summer` | March – June |
| `winter` | December – February |

### Duplicate Suppression Windows

| Metric Type | Suppression Window |
|---|---|
| Earthquake | 0 min (each event is unique by `usgs_event_id`) |
| Temperature | 180 min (3 hours) |
| Rainfall | 120 min (2 hours) |
| Wind | 60 min (1 hour) |
| Flood Gauge | 60 min (1 hour) |

### Breach Lifecycle

```
Breach detected
    └──► INSERT into threshold_breach_log (status: 'pending')
              └──► DispatchService (every 30s)
                        ├── POST /alerts/incoming → Main System
                        │         ├── 200/201 ── mark_dispatched ✅
                        │         └── error ──── mark_dispatch_failed (retry up to 5x) ❌
                        └── After 5 failures → requires manual intervention
```

---

## ⏰ Scheduled Jobs

| # | Job ID | Trigger | Function |
|---|--------|---------|----------|
| 1 | `usgs_collection` | Every 60s | Poll USGS for earthquakes ≥ M2.5 in Pakistan |
| 2 | `weather_collection` | Every 15 min | Poll Open-Meteo for all 15 locations |
| 3 | `flood_current` | Every 30 min | Fetch current river levels from 10 gauges |
| 4 | `flood_forecasts` | Every 6 h | Fetch probabilistic flood forecasts |
| 5 | `breach_dispatch` | Every 30 s | Dispatch pending breach alerts to main system |
| 6 | `threshold_reload` | Every 1 h | Reload thresholds & locations from Supabase |
| 7 | `daily_cleanup` | 00:05 PKT | Delete expired rolling-window data |

**All jobs are wrapped with `_safe_job_wrapper()`** — one failure never crashes the scheduler.

---

## 🔌 API Endpoints

All endpoints require the `X-API-Key` header matching `MAIN_SYSTEM_API_KEY`.

### Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Service status, DB connectivity, uptime |
| `GET` | `/health/apis` | Per-API health, consecutive failures, backoff state |

**`GET /health` — Example Response:**
```json
{
  "status": "healthy",
  "database_connected": true,
  "uptime_seconds": 3600.5,
  "timestamp_pkt": "2026-10-19T12:00:00+05:00"
}
```

**`GET /health/apis` — Example Response:**
```json
{
  "apis": [
    {
      "api_name": "usgs",
      "display_name": "USGS Earthquake API",
      "current_health": "healthy",
      "last_success_at": "2026-10-19T11:59:00+05:00",
      "last_failure_at": null,
      "consecutive_failures": 0,
      "is_in_backoff": false,
      "backoff_remaining_seconds": null
    }
  ],
  "timestamp_pkt": "2026-10-19T12:00:00+05:00"
}
```

### Status

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/status/cycles` | Last 10 collection cycles per API |
| `GET` | `/status/breaches` | Breach counts by dispatch status + last breach time |
| `GET` | `/status/locations` | Per-location polling status and failure count |

### Other

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Service info and endpoint listing |
| `POST` | `/trigger/usgs` | Manually trigger USGS collection (testing) |

---

## 📁 Project Structure

```
Data_collection/
│
├── main.py                        # Entry point
├── pyproject.toml                 # Dependencies (uv/pip)
├── .env.example                   # All required environment variables
├── database_schema.sql            # Full Supabase schema reference
│
├── app/
│   ├── main.py                    # FastAPI app + lifespan startup/shutdown
│   │
│   ├── core/
│   │   ├── config.py              # pydantic-settings — single source of .env truth
│   │   ├── logger.py              # Structured JSON logging (PKT timezone)
│   │   ├── exceptions.py          # Custom exception hierarchy
│   │   └── security.py            # Constant-time API key validation
│   │
│   ├── database/
│   │   ├── connection.py          # asyncpg pool manager (only file using asyncpg)
│   │   └── queries/               # Raw SQL strings (one file per domain)
│   │       ├── seismic_queries.py
│   │       ├── weather_queries.py
│   │       ├── flood_queries.py
│   │       ├── breach_queries.py
│   │       ├── cycle_queries.py
│   │       └── reference_queries.py
│   │
│   ├── models/                    # Pydantic data models (no DB logic)
│   │   ├── reference_models.py    # ApiRegistry, DisasterThreshold, PakistanLocation
│   │   ├── seismic_models.py      # SeismicEventBase, SeismicEvent
│   │   ├── weather_models.py      # WeatherHourlyWindow, WeatherDailySummary
│   │   ├── flood_models.py        # FloodGaugeRegistry, FloodGaugeCurrent, FloodGaugeForecast
│   │   ├── breach_models.py       # ThresholdBreachLog
│   │   └── cycle_models.py        # CollectionCycle
│   │
│   ├── repositories/              # Database access layer (one per domain)
│   │   ├── base_repository.py
│   │   ├── reference_repository.py
│   │   ├── seismic_repository.py
│   │   ├── weather_repository.py
│   │   ├── flood_repository.py
│   │   ├── breach_repository.py
│   │   └── cycle_repository.py
│   │
│   ├── collectors/                # External API polling
│   │   ├── base_collector.py      # Retry, backoff, counters (base class)
│   │   ├── usgs_collector.py      # USGS earthquakes
│   │   ├── openmeteo_collector.py # Open-Meteo weather
│   │   └── floodhub_collector.py  # Google Flood Hub
│   │
│   ├── services/                  # Business logic
│   │   ├── breach_service.py      # ⭐ Threshold detection (used by ALL collectors)
│   │   ├── usgs_service.py        # Parse + process earthquake GeoJSON
│   │   ├── openmeteo_service.py   # Parse + process weather forecast
│   │   ├── floodhub_service.py    # Parse + process flood gauge data
│   │   └── dispatch_service.py    # Send breach alerts to main system
│   │
│   ├── scheduler/
│   │   └── job_scheduler.py       # APScheduler wrapper with 7 jobs
│   │
│   └── api/routes/
│       ├── health_controller.py   # GET /health, /health/apis
│       └── status_controller.py   # GET /status/cycles, /breaches, /locations
│
├── tests/                         # 130+ unit tests (pytest)
│   ├── test_breach_service.py
│   ├── test_base_collector.py
│   ├── test_usgs_service.py
│   ├── test_usgs_collector.py
│   ├── test_openmeteo_service.py
│   ├── test_openmeteo_collector.py
│   ├── test_health_controller.py
│   ├── test_status_controller.py
│   └── test_main.py
│
└── docs/
    ├── Getting_Started_Guide.md
    ├── USGS_Implementation.md
    ├── OpenMeteo_Implementation.md
    └── FloodHub_Implementation.md
```

---

## 🚀 Getting Started

### Prerequisites

- Python **3.12+**
- [`uv`](https://docs.astral.sh/uv/) package manager (recommended) or `pip`
- A Supabase project with the schema applied (`database_schema.sql`)
- A Google Cloud project with Flood Hub API enabled

### 1. Clone the Repository

```bash
git clone https://github.com/your-org/climasync-data-collection.git
cd climasync-data-collection
```

### 2. Install Dependencies

```bash
# Using uv (recommended)
uv sync

# Or using pip
pip install -e .
```

### 3. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your actual values — see [Environment Variables](#-environment-variables) below.

### 4. Apply Database Schema

Run `database_schema.sql` against your Supabase project using the SQL Editor or `psql`.

### 5. Run the Service

```bash
# Using uv
uv run python main.py

# Or with uvicorn directly
uv run uvicorn app.main:app --reload --port 8000
```

The service starts on `http://0.0.0.0:8000`. Check startup logs — 7 steps should complete before the first API request.

---

## 🔧 Environment Variables

Copy `.env.example` to `.env` and fill in all values. Required fields are marked with `*`.

### Database (Supabase)

| Variable | Default | Description |
|---|---|---|
| `COLLECTION_DB_HOST` * | — | Supabase pooler hostname |
| `COLLECTION_DB_PORT` | `5432` | Database port |
| `COLLECTION_DB_NAME` | `postgres` | Database name |
| `COLLECTION_DB_USER` * | — | Database user |
| `COLLECTION_DB_PASSWORD` * | — | Database password |
| `COLLECTION_DB_POOL_MIN` | `2` | Min pool connections |
| `COLLECTION_DB_POOL_MAX` | `10` | Max pool connections |

### Main System Connection

| Variable | Default | Description |
|---|---|---|
| `MAIN_SYSTEM_BASE_URL` * | — | Main ClimaSync API base URL |
| `MAIN_SYSTEM_API_KEY` * | — | Shared API key for internal auth |

### External APIs

| Variable | Default | Description |
|---|---|---|
| `USGS_BASE_URL` | `https://earthquake.usgs.gov/fdsnws/event/1/query` | USGS API endpoint |
| `OPENMETEO_BASE_URL` | `https://api.open-meteo.com/v1/forecast` | Open-Meteo endpoint |
| `GOOGLE_FLOOD_HUB_BASE_URL` | `https://floodhub.googleapis.com/v1` | Flood Hub endpoint |
| `GOOGLE_FLOOD_HUB_API_KEY` * | — | Google Cloud API key |

### Collection Intervals

| Variable | Default | Description |
|---|---|---|
| `USGS_POLL_INTERVAL_SECONDS` | `60` | Earthquake polling frequency |
| `OPENMETEO_POLL_INTERVAL_MINUTES` | `15` | Weather polling frequency |
| `FLOOD_CURRENT_INTERVAL_MINUTES` | `30` | Flood current readings |
| `FLOOD_FORECAST_INTERVAL_HOURS` | `6` | Flood forecast polling |
| `BREACH_DISPATCH_INTERVAL_SECONDS` | `30` | Alert dispatch frequency |
| `THRESHOLD_RELOAD_INTERVAL_HOURS` | `1` | Cache reload frequency |
| `CLEANUP_HOUR_PKT` | `0` | Daily cleanup hour (PKT) |
| `CLEANUP_MINUTE_PKT` | `5` | Daily cleanup minute (PKT) |

### Collection Settings

| Variable | Default | Description |
|---|---|---|
| `USGS_MIN_MAGNITUDE` | `2.5` | Minimum earthquake magnitude |
| `USGS_LOOKBACK_HOURS` | `6` | Lookback window for USGS updates |
| `MAX_DISPATCH_ATTEMPTS` | `5` | Max retries per breach dispatch |
| `DISPATCH_BATCH_SIZE` | `10` | Breaches dispatched per cycle |

### Application

| Variable | Default | Description |
|---|---|---|
| `APP_PORT` | `8000` | Service port |
| `APP_ENV` | `development` | `development` or `production` |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `SERVICE_NAME` | `climasync-collection` | Identifier in logs |

---

## 🗄️ Database Schema

Key tables managed by this service:

| Table | Rolling Window | Description |
|---|---|---|
| `pakistan_locations` | Static | 15 monitored cities and districts |
| `disaster_thresholds` | Static | Threshold rules per metric/region/season |
| `api_registry` | Live | API health, backoff state, rate limit tracking |
| `flood_gauge_registry` | Static | 10 river gauge definitions |
| `seismic_events` | 30 days | Earthquake events (UPSERT by `usgs_event_id`) |
| `weather_hourly_window` | 7 days | Hourly weather data per location |
| `weather_daily_summary` | 14 days | Daily weather summaries per location |
| `flood_gauge_current` | Latest | Most recent river level per gauge |
| `flood_gauge_forecasts` | 7 days | Probabilistic flood forecasts (p10/p50/p90) |
| `threshold_breach_log` | Permanent | All detected breaches + dispatch lifecycle |
| `collection_cycles` | Permanent | Per-API cycle metrics and status |

See `database_schema.sql` for the complete schema with all columns, indexes, and constraints.

---

## 🧪 Running Tests

```bash
# Run all tests
uv run pytest

# With coverage report
uv run pytest --cov=app --cov-report=term-missing

# Run a specific test module
uv run pytest tests/test_breach_service.py -v
```

### Test Coverage

| Module | Tests | Status |
|---|---|---|
| `breach_service` | 24 | ✅ All passing |
| `base_collector` | 24 | ✅ All passing |
| `usgs_service` + `usgs_collector` | 24 | ✅ All passing |
| `openmeteo_service` + `openmeteo_collector` | 40 | ✅ All passing |
| `health_controller` | 10 | ✅ All passing |
| `status_controller` | 12 | ✅ All passing |
| `main` (startup/shutdown) | 6 | ✅ All passing |
| **Total** | **140+** | ✅ |

---

## 🛠️ Tech Stack

| Library | Version | Purpose |
|---|---|---|
| [FastAPI](https://fastapi.tiangolo.com/) | ≥0.135 | Web framework + OpenAPI docs |
| [Uvicorn](https://www.uvicorn.org/) | ≥0.44 | ASGI server |
| [asyncpg](https://magicstack.github.io/asyncpg/) | ≥0.31 | Async PostgreSQL driver |
| [httpx](https://www.python-httpx.org/) | ≥0.28 | Async HTTP client |
| [APScheduler](https://apscheduler.readthedocs.io/) | ≥3.11 | Job scheduling |
| [Pydantic](https://docs.pydantic.dev/) | ≥2.12 | Data validation and models |
| [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) | ≥2.13 | Environment variable management |
| [Tenacity](https://tenacity.readthedocs.io/) | ≥9.1 | Retry logic with exponential backoff |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | ≥1.2 | `.env` file loading |
| [tzdata](https://pypi.org/project/tzdata/) | ≥2026.1 | Timezone data (Asia/Karachi) |

**Dev dependencies:**
- `pytest` ≥9.0, `pytest-asyncio` ≥1.3, `pytest-cov` ≥7.1, `anyio` ≥4.13

---

## 🔐 Security

- **API key auth:** All `/health` and `/status` endpoints are protected with `X-API-Key` header validation using constant-time comparison (prevents timing attacks).
- **No secrets in code:** All credentials loaded exclusively from `.env` — never hardcoded.
- **SSL required:** Database connections enforce `ssl="require"` — no plaintext connections.
- **Internal-only dispatch:** Breach alerts sent only to `MAIN_SYSTEM_BASE_URL` with the configured API key.

---

## 📋 Error Handling

```
CollectionServiceError (base)
├── ApiRateLimitError    — HTTP 429; triggers configurable backoff stored in DB
├── ApiTimeoutError      — Request timeout exceeded
├── ApiResponseError     — Unexpected HTTP status (non-2xx, non-429)
├── DatabaseError        — asyncpg operation failure
│   └── DatabaseConnectionError  — Pool creation or connectivity failure
├── BreachDetectionError — Invalid threshold configuration
├── DispatchError        — Breach alert dispatch failure
└── ConfigurationError   — Missing or invalid .env variable (blocks startup)
```

Rate limit backoff state is persisted to the `api_registry` table — so a restarted service won't hammer a rate-limited API.

---

## 📄 License

This project is licensed under the MIT License.

---

<div align="center">

**Built for ClimaSync.ai** · Pakistan Early Warning System  
*Monitoring 15 cities · 3 data sources · 21 disaster thresholds · 10 river gauges*

</div>
