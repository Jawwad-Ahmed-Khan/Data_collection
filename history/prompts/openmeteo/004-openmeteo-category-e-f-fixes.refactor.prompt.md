---
id: 004
title: Open-Meteo Category E & F Fixes
stage: refactor
date: 2026-05-11
surface: agent
model: gemini
feature: openmeteo
user: jawad
command: /sp.phr
labels: ["bugfix", "open-meteo", "database", "null-safety", "performance"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
  - d:\Projects\Data_collection\app\services\openmeteo_service.py
  - d:\Projects\Data_collection\app\repositories\weather_repository.py
  - d:\Projects\Data_collection\app\database\queries\weather_queries.py
tests:
  - None
---

# Prompt

implement it solve
solve it

# Response

I implemented all the updates defined in the implementation plan for Categories E and F:
1. **Null Safety**: Replaced all instances of `or Decimal("0.0")` for core variables with strict `None` preservation. Now, if Open-Meteo returns null, the system forwards Python `None` to the database, ensuring Postgres accurately saves it as `NULL`.
2. **Data Clamping & Validation**: Added integer casting and bounds checking `max(0, min(100, val))` to probability and coverage percentages, and guaranteed strictly typed conversion for boolean and integers.
3. **Rolling Precipitation**: Rewrote `_compute_rolling_sums` to operate directly on the raw API array list of floats. It now correctly identifies when an entire window is comprised of `None` values and accurately propagates `None` instead of evaluating to `0.0`.
4. **Trigger Alignment**: Pruned `weather_condition`, `wind_direction_cardinal`, `day_offset`, and `forecast_date` from the hourly UPSERT query so they don't explicitly override or conflict with the established Postgres triggers. Added `RETURNING (xmax = 0) AS was_inserted`.
5. **Batch Inserts**: Scrapped the 120 individual sequential inserts per location. Implemented `executemany` inside the `upsert_hourly_batch` and `upsert_daily_batch` repository methods. This provides substantial operational performance gains and transaction safety for the Collector.
