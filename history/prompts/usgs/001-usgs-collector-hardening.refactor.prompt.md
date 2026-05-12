---
id: "001"
title: "usgs-collector-hardening"
stage: "refactor"
date: "2026-05-12"
surface: "agent"
model: "gemini"
feature: "usgs"
branch: "none"
user: "jawad"
command: "sp.phr"
labels:
  - "reliability"
  - "usgs"
  - "bugfix"
links:
  spec: "null"
  ticket: "null"
  adr: "null"
  pr: "null"
files:
  - "app/collectors/usgs_collector.py"
  - "app/services/usgs_service.py"
tests:
  - "Manual Review"
---

## Prompt

Now you provide me prompts current only for USGS in AI analyze all code determine issues, problems working and resolve all problems that my usgs service work all time not stop or going down

Ok immplenet it

## Response

- Generated the `usgs_implementation_plan.md` outlining missing `ApiRateLimitError` imports, missing `exc_info=True` traceback logs, and missing `Decimal` coercions in Pydantic.
- Replaced floating-point extractions with `to_decimal` wrapper for `magnitude`, `depth_km`, `cdi`, and `mmi`.
- Included `ApiRateLimitError` import in `usgs_collector.py`.
- Added `exc_info=True` for database insertion error loops.
- Created `usgs_final_report.md` summarizing the 13-step framework evaluation.
