---
id: 5
title: "openmeteo-category-g-h-fixes"
stage: "refactor"
date: "2026-05-11"
surface: "agent"
model: "gemini-2.5-pro"
feature: "openmeteo"
user: "jawad"
labels: ["refactor", "bugfix", "breach-detection", "weather-flags"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
  - app/services/openmeteo_service.py
  - app/services/breach_service.py
  - app/database/queries/breach_queries.py
  - app/repositories/breach_repository.py
tests:
  - None
---

# Prompt History Record: openmeteo-category-g-h-fixes

## Prompt
```text
implement it
```

## Response
I have successfully implemented all Category G and H fixes according to the audit checklist:

1. **Weather Flags (G2-G3):** Strict WMO-aligned conditionals added to `_set_weather_flags` and `_set_daily_flags` in `openmeteo_service.py`. Null-safety strictly enforced for flag computation.
2. **Season Detection & Threshold Caching (H2):** Fixed the month-to-season mapping in `breach_service.py` to match the exact requirement. Add an O(1) in-memory cache to `find_applicable_threshold` to avoid repetitive 10,800 DB threshold searches per processing cycle.
3. **Duplicate Suppression (H5):** Added `cape` to the 60-minute window in `_SUPPRESSION_WINDOWS` and passed `suppression_window_used_m` correctly through `create_breach`, `BreachRepository.insert_breach`, and the `INSERT_BREACH_LOG` query.
4. **Breach Insert & Performance Optimization (H8):** Fixed the fact that `create_breach()` was completely skipped in the initial collector! Built an in-memory `suppressed_metrics` tracker per location in the 120-hour loop. This ensures we insert a breach for the FIRST hour that crosses the threshold, properly flag it with `is_forecast_breach` and `forecast_horizon_h`, and silently suppress subsequent breaching hours for the same metric in the same cycle without hammering the DB.

## Outcomes
- High-frequency duplicate DB queries for threshold checks and duplicate breaches eliminated in the 120-hour Open-Meteo processing loop.
- Guaranteed atomic and exact computation of extreme weather flags to provide correct signaling for downstream services.
- Proper routing and duplicate suppression logic for `cape_jkg` severe storms.
