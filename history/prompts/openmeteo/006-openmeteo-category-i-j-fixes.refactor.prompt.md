---
id: 006
title: "openmeteo-category-i-j-fixes"
stage: refactor
date: 2026-05-12
surface: agent
model: gemini
feature: openmeteo
branch: main
user: Jawwad-Ahmed-Khan
labels:
  - cycle-management
  - scheduler-reliability
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
  - app/collectors/openmeteo_collector.py
  - app/scheduler/job_scheduler.py
  - app/repositories/cycle_repository.py
  - app/database/queries/cycle_queries.py
tests:
  - null
---

# Prompt

I already perfrom this fixes all fixes detail in D:\Projects\Data_collection\history\prompts\openmeteo 
now move this fixe
STEP 9 — AUDIT CATEGORY I: CYCLE MANAGEMENT
...
STEP 10 — AUDIT CATEGORY J: SCHEDULER RELIABILITY
...

# Response

Executed the requested refactoring for Cycle Management (Category I) and Scheduler Reliability (Category J). This included:
- Modifying `INSERT_CYCLE` and `UPDATE_CYCLE` to track `cycle_type` and `avg_latency_ms`.
- Updating `CycleRepository` to accept these parameters.
- Refactoring `OpenMeteoCollector.collect()` to check API backoff before continuing, tracking per-location errors, and capturing cycle-level average API latency.
- Updating `JobScheduler`'s `weather_collection` job with `max_instances=1`, `coalesce=True`, and setting `next_run_time` to immediately fire on startup.
