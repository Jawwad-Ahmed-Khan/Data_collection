---
id: 003
title: "Flood Hub Step 16 Bug Patterns Audit"
stage: "refactor"
date: "2026-05-12"
surface: "agent"
model: "gemini"
feature: "floodhub"
branch: "none"
user: "jawad"
command: "Flood Hub Specific Bug Patterns"
labels: ["flood", "bug-fixes", "verification"]
links:
  spec: "null"
  ticket: "null"
  adr: "null"
  pr: "null"
files:
  - app/collectors/floodhub_collector.py
  - app/services/floodhub_service.py
  - app/database/queries/flood_queries.py
  - database_schema.sql
tests:
  - none
---

# Prompt History Record

## Prompt Text
STEP 16 — SPECIFIC BUG PATTERNS FOR FLOOD HUB
BUG 1: Fetching previous reading AFTER upsert
...
BUG 14: Forecast issued_at timezone
... (Full prompt verbatim applied)

## Response Text
Audited the entire Flood Hub collector module against the 14 specific bug patterns provided in Step 16. Verified that all patterns had already been correctly implemented or mitigated during previous refactoring rounds. 
Specifically confirmed:
- `UPSERT_FLOOD_CURRENT` correctly excludes `coordinates`.
- `UPSERT_FLOOD_FORECAST` explicitly excludes trigger-managed fields (`day_offset`, `forecast_date`, `forecast_horizon_h`).
- Time parsing uses timezone-aware conversions natively.
- Foreign key cascading acts appropriately across `flood_gauge_current` (CASCADE) and `threshold_breach_log` (SET NULL).
- No blocking or incorrectly-flagged loops exist in collection logic.

## Outcome/Evaluation
Pass. All 14 specific bug patterns for Flood Hub have been successfully verified as absent from the current codebase. The system behaves defensively and securely against these known edge cases.
