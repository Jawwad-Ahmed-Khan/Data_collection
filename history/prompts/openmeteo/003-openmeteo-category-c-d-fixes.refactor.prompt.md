---
id: 003
title: Open-Meteo Category C & D Fixes
stage: refactor
date: 2026-05-11
surface: agent
model: gemini
feature: openmeteo
user: jawad
command: /sp.phr
labels: ["bugfix", "open-meteo", "datetime", "api-params"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
  - d:\Projects\Data_collection\app\services\openmeteo_service.py
  - d:\Projects\Data_collection\app\collectors\base_collector.py
tests:
  - None
---

# Prompt

pls update i required only 120 hours pls correct it
solve issues

# Response

I have reverted the Open-Meteo parameters to strictly request 5 days without historical data (`past_days` removed), meaning it explicitly receives and parses exactly 120 hourly forecasts and 5 daily forecasts.

I also resolved the core issues identified in Categories C & D:
1. **API Parameters**: Added missing `wind_speed_unit` and `precipitation_unit`. Swapped `surface_pressure` out for `pressure_msl` to match requirements.
2. **Datetime Parsing (CRITICAL FIX)**: Previously, timestamps were generated locally as PKT (`Asia/Karachi`) but saved directly into the database's UTC `TIMESTAMPTZ` column. This resulted in an invisible 5-hour offset which severely breaks day boundary matching and trigger validation. It now performs `naive_dt.replace(tzinfo=PKT).astimezone(timezone.utc)` for hourly records, sunrise, and sunset.
3. **Response Validation**: Inserted active validation on hourly (120) and daily (5) array lengths.
4. **Resiliency Tuning**: Implemented the precise `httpx` timeouts (`connect=10.0`) and updated the `tenacity` exponential backoff (`min=2`) inside the BaseCollector.
5. **Window Boundaries**: Enforced a strict window bound of `0 <= day_offset <= 4` to prevent any potential trigger exceptions from halting the entire batch.
