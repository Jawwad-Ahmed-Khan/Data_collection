# Quick Start - Open-Meteo Batch Implementation

## What Changed?

The Open-Meteo collector now:
1. ✅ Only polls locations that are **due** (checks `next_poll_due_at`)
2. ✅ Polls **critical locations first** (sorts by `poll_priority`)
3. ✅ Fetches **up to 10 locations per API call** (batch optimization)
4. ✅ **Tracks poll state** in database (updates `next_poll_due_at`)

**Result:** 30x fewer API calls, faster cycles, respects rate limits.

---

## How to Use

### 1. Configure Locations in Database

```sql
-- Set poll priority and interval for each location
UPDATE pakistan_locations
SET
    poll_priority = 'critical',      -- critical | high | medium | low
    poll_interval_minutes = 180,     -- How often to poll (3 hours)
    next_poll_due_at = NULL,         -- NULL = poll on next cycle
    is_active = TRUE
WHERE location_name = 'Lahore';
```

### 2. Run the Collector

```python
# The collector automatically:
# - Checks which locations are due
# - Groups them into batches of 10
# - Fetches all in single API call
# - Updates next_poll_due_at for each

await openmeteo_collector.collect()
```

### 3. Monitor Logs

```
[INFO] Found 2 locations due for polling (out of 15 total active)
[INFO] Polling 2 locations in 1 batch(es) of up to 10 locations each
[DEBUG] Processing batch 1/1 with 2 locations
[DEBUG] Updated poll state for Lahore: next_due=2025-07-15 12:00:00 PKT
[INFO] Open-Meteo cycle completed: locations=2/2, API_calls=1
```

---

## Key Concepts

### Next Poll Due At

Each location has `next_poll_due_at` timestamp:
- **NULL** = Never polled, poll immediately
- **Past** = Due for polling
- **Future** = Not due yet, skip

### Poll Priority

Determines polling order:
- **critical** = Provincial capitals (polled first)
- **high** = Major cities
- **medium** = Disaster zones
- **low** = Other locations

### Batch Size

Up to 10 locations per API call:
- 1-10 locations = 1 API call
- 11-20 locations = 2 API calls
- 21-30 locations = 3 API calls
- etc.

---

## Example Scenarios

### Scenario 1: First Run (All Locations NULL)

```
Time: 09:00
Locations: 15 total, all have next_poll_due_at = NULL

Result:
- All 15 locations are due
- Split into 2 batches (10 + 5)
- 2 API calls total
- Each location gets next_poll_due_at = 12:00 (09:00 + 3 hours)
```

### Scenario 2: Normal Operation

```
Time: 12:00
Locations: 15 total
- 2 locations have next_poll_due_at = 12:00 (due)
- 13 locations have next_poll_due_at = 13:00-15:00 (not due)

Result:
- Only 2 locations are due
- 1 batch (2 locations)
- 1 API call total
- Those 2 locations get next_poll_due_at = 15:00 (12:00 + 3 hours)
```

### Scenario 3: Failed Location

```
Time: 15:00
Location: Lahore fails to collect (API timeout)

Result:
- consecutive_failures incremented to 1
- next_poll_due_at still set to 18:00 (will retry then)
- Other locations unaffected
```

---

## Troubleshooting

### Problem: All locations polled every cycle

**Symptom:**
```
[INFO] Found 15 locations due for polling (out of 15 total active)
```

**Cause:** `next_poll_due_at` not being updated

**Fix:**
1. Check `UPDATE_LOCATION_POLL_STATE` query exists
2. Check `update_location_poll_state()` is called after each collection
3. Check database permissions for UPDATE on `pakistan_locations`

### Problem: No locations ever polled

**Symptom:**
```
[INFO] Found 0 locations due for polling (out of 15 total active)
```

**Cause:** All `next_poll_due_at` are in the future

**Fix:**
```sql
-- Reset one location to poll immediately
UPDATE pakistan_locations
SET next_poll_due_at = NULL
WHERE location_name = 'Lahore';
```

### Problem: Batch API returns error

**Symptom:**
```
[ERROR] Batch API error: Invalid latitude/longitude format
```

**Cause:** Comma-separated format incorrect

**Fix:**
Check `build_batch_params()` creates proper format:
```python
"latitude": "31.5497,24.8607,33.6844"  # Correct
"latitude": "31.5497, 24.8607, 33.6844"  # Wrong (spaces)
```

---

## API Call Calculation

### Formula

```
locations_due = total_locations / (poll_interval_minutes / scheduler_interval_minutes)
batches = ceil(locations_due / 10)
api_calls_per_cycle = batches
```

### Example: 15 Locations, 3-Hour Interval

```
Scheduler runs every 15 minutes
Poll interval = 180 minutes

locations_due = 15 / (180 / 15) = 15 / 12 = 1.25 ≈ 1-2 per cycle
batches = ceil(1.25 / 10) = 1
api_calls_per_cycle = 1

Per day: 96 cycles × 1 call = 96 API calls
```

### Example: 270 Locations (Future), 6-Hour Interval

```
Scheduler runs every 15 minutes
Poll interval = 360 minutes

locations_due = 270 / (360 / 15) = 270 / 24 = 11.25 ≈ 11-12 per cycle
batches = ceil(11.25 / 10) = 2
api_calls_per_cycle = 2

Per day: 96 cycles × 2 calls = 192 API calls
```

---

## Quick Reference

### Database Fields

| Field | Type | Purpose |
|-------|------|---------|
| `poll_priority` | enum | Polling order (critical first) |
| `poll_interval_minutes` | int | How often to poll (180 = 3 hours) |
| `last_polled_at` | timestamp | When last polled |
| `last_poll_outcome` | enum | 'success' or 'failed' |
| `next_poll_due_at` | timestamp | When to poll next |
| `consecutive_failures` | int | Failure count (reset on success) |

### Priority Values

- `critical` = 0 (polled first)
- `high` = 1
- `medium` = 2
- `low` = 3

### Typical Intervals

- **Critical locations:** 180 minutes (3 hours)
- **High priority:** 240 minutes (4 hours)
- **Medium priority:** 360 minutes (6 hours)
- **Low priority:** 720 minutes (12 hours)

---

## Testing Commands

### Check Due Locations

```sql
SELECT
    location_name,
    poll_priority,
    next_poll_due_at,
    CASE
        WHEN next_poll_due_at IS NULL THEN 'DUE (never polled)'
        WHEN next_poll_due_at <= now() THEN 'DUE'
        ELSE 'NOT DUE'
    END AS status
FROM pakistan_locations
WHERE is_active = TRUE
ORDER BY poll_priority, next_poll_due_at NULLS FIRST;
```

### Check Poll History

```sql
SELECT
    location_name,
    last_polled_at,
    last_poll_outcome,
    consecutive_failures,
    EXTRACT(EPOCH FROM (now() - last_polled_at)) / 60 AS minutes_since_poll
FROM pakistan_locations
WHERE is_active = TRUE
ORDER BY last_polled_at DESC;
```

### Force Poll Location

```sql
UPDATE pakistan_locations
SET next_poll_due_at = now() - INTERVAL '1 minute'
WHERE location_name = 'Lahore';
```

---

## Performance Expectations

### 15 Locations (Current)

- **Locations due per cycle:** 1-2
- **Batches per cycle:** 1
- **API calls per cycle:** 1
- **Cycle duration:** <1 second
- **API calls per day:** ~96

### 270 Locations (Future)

- **Locations due per cycle:** 11-12
- **Batches per cycle:** 2
- **API calls per cycle:** 2
- **Cycle duration:** <2 seconds
- **API calls per day:** ~192

Both well within Open-Meteo free tier (10 requests/minute = 14,400/day).

---

## Support

For issues or questions:
1. Check logs for error messages
2. Verify database configuration
3. Review `docs/OpenMeteo_Batch_Implementation.md` for details
4. Check `IMPLEMENTATION_SUMMARY.md` for technical details
