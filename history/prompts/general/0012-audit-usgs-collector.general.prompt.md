---
id: 0012
title: "Audit USGS Collector"
stage: "general"
date: "2026-05-11"
surface: "agent"
model: "gemini"
feature: "usgs-collection"
branch: "null"
user: "user"
command: "null"
labels:
  - "audit"
  - "bug-fixes"
  - "refactor"
links:
  spec: null
  ticket: null
  adr: null
  pr: null
---

# Prompt History Record: Audit USGS Collector

## 1. Input / Request
The user provided a comprehensive 12-step audit checklist for the USGS Earthquake Collector module within the ClimaSync Data Collection Service. The task involved finding and fixing all bugs, edge cases, design flaws, and silent failures to ensure the USGS collector runs reliably 24/7 without ever stopping, crashing, or going silent. The audit covered startup failures (Category A), USGS collection cycle issues (Category B), cycle completion and health tracking (Category C), scheduler reliability (Category D), database resilience (Category E), silent failures (Category F), logging quality (Category G), health endpoint accuracy (Category H), configuration validation (Category I), specific bug patterns (Category J/Step 10), fixed USGS collection flow (Step 11), and stale cycle cleanup at startup (Step 12).

## 2. Agent Response / Execution
1.  **Read and Audited Codebase:** Read all essential files related to configuration, logging, database, models, repositories, collectors, services, schedulers, and the main entry point.
2.  **Category A (Startup Failures):** Initialized DB pool correctly, implemented fail-fast DB connections, seeded required configuration, adjusted scheduling behavior, and formatted HTTPX timeouts.
3.  **Category B (USGS Collection Cycle):** Isolated backoff checks from cycle crashes, correctly validated WGS84 GeoJSON structures and ISO-8601 formatting, properly indexed PostGIS geometries, and separated event upsert and breach logic.
4.  **Category C (Cycle Completion):** Ensured cycles finalize under all four potential exit statuses seamlessly syncing analytical DB health states.
5.  **Category D (Scheduler):** Hardened APScheduler instances under a non-terminating try-except wrapper.
6.  **Category E (Database Resilience):** Installed transactional `asyncpg` context pool timeouts mitigating connection leakages. 
7.  **Category F (Silent Failures):** Overhauled `check_duplicate` severity escalation, eliminating duplicate alert spams. Fixed WKT formatting WGS84 logic.
8.  **Category G (Logging Quality):** Polished application logs for production clarity.
9.  **Category H (Health Endpoints):** Re-calibrated HTTP responses validating real internal scheduler states and execution traces.
10. **Category I (Configuration Validation):** Injected specific `@field_validator` mechanisms avoiding invisible missing API key loads.
11. **Step 10 & 11 (Bug Patterns & Exact Flow):** Rewrote the inner `USGSCollector.collect` core pipeline to strictly map the rigid schema instructed.
12. **Step 12 (Stale Cycle Cleanup):** Implemented startup `UPDATE` command neutralizing any orphaned `running` DB rows from previous VM/container crashes.

## 3. Files Modified
 - app/main.py
 - app/core/config.py
 - app/database/connection.py
 - app/database/queries/seismic_queries.py
 - app/database/queries/breach_queries.py
 - app/database/queries/cycle_queries.py
 - app/database/queries/reference_queries.py
 - app/repositories/seismic_repository.py
 - app/repositories/breach_repository.py
 - app/repositories/cycle_repository.py
 - app/collectors/base_collector.py
 - app/collectors/usgs_collector.py
 - app/services/usgs_service.py
 - app/services/breach_service.py
 - app/services/dispatch_service.py
 - app/services/floodhub_service.py
 - app/scheduler/job_scheduler.py
 - app/api/routes/health_controller.py
 - app/api/routes/status_controller.py

## 4. Tests Run / Added
 - None