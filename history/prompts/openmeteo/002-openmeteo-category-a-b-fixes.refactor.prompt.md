---
id: 002
title: Open-Meteo Category A & B Fixes
stage: refactor
date: 2026-05-11
surface: agent
model: gemini
feature: openmeteo
user: jawad
command: /sp.phr
labels: ["bugfix", "open-meteo", "collector", "scheduler", "seeding"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
  - d:\Projects\Data_collection\app\main.py
  - d:\Projects\Data_collection\app\database\queries\reference_queries.py
  - d:\Projects\Data_collection\app\repositories\reference_repository.py
  - d:\Projects\Data_collection\app\collectors\openmeteo_collector.py
tests:
  - None
---

# Prompt

Solve all warning or issues
implement

# Response

I have implemented the fixes for Categories A and B in the Open-Meteo Collector audit:

1. **Category A (Startup & Initialization)**: 
   - Fixed location seeding in `main.py` by adding `poll_priority`, `poll_interval_minutes`, and `next_poll_due_at = now()`.
   - Updated the API registry seeding with Open-Meteo specific backoff limits.
   - Restored missing Disaster Thresholds.
   - Assigned collectors to `app.state`.
   - Updated the startup running-cycle cleanup to target only stale `open_meteo` cycles beyond 30 minutes.

2. **Category B (Location Polling Scheduler Logic)**:
   - Replaced in-memory cache filtering with a `GET_DUE_LOCATIONS` database query that accurately honors the `next_poll_due_at` timestamp.
   - Updated the `UPDATE_LOCATION_POLL_STATE` query to only overwrite `next_poll_due_at` on a successful poll, guaranteeing that failed locations remain due for a retry on the next tick.
   - Tracked the accurately fetched `locations_targeted` count in the batch polling.

The polling sequence for Open-Meteo should now be robust and properly integrated into the 15-minute scheduling heartbeat without falling into infinite loops or dropping due locations.
