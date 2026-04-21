# Open-Meteo Batch API Implementation

## Overview

This document explains the optimized Open-Meteo collector implementation that addresses the critical requirements:

1. ✅ **Check `next_poll_due_at` before polling** - Only poll locations that are due
2. ✅ **Priority-based polling** - Critical locations polled first
3. ✅ **Batch API optimization** - Fetch up to 10 locations per API call (10x reduction)
4. ✅ **Poll state tracking** - Update database after each collection attempt

---

## Key Improvements

### 1. Smart Location Filtering

**Before:**
```python
# ❌ Polled ALL active locations every time
for location in self.pakistan_locations:
    if location.is_active:
        due_locations.append(location)
```

**After:**
```python
# ✅ Only poll locations that are due
for location in self.pakistan_locations:
    if not location.is_active:
        continue
    
    # Check if due: next_poll_due_at is None OR next_poll_due_at <= now
    if location.next_poll_due_at is None or location.next_poll_due_at <= now:
        due_locations.append(location)
```

**Impact:**
- Reduces API calls by 10-24x (only polls every 3-6 hours instead of every 15 minutes)
- Respects Open-Meteo rate limits
- Prevents unnecessary data refreshes

---

### 2. Priority-Based Sorting

**Before:**
```python
# ❌ Sorted by location name
due_locations.sort(key=lambda loc: loc.location_name)
```

**After:**
```python
# ✅ Sort by poll_priority (critical > high > medium > low)
priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
due_locations.sort(
    key=lambda loc: priority_order.get(
        getattr(loc, 'poll_priority', 'medium'), 
        2
    )
)
```

**Impact:**
- Provincial capitals (critical) polled first
- Major cities (high) polled second
- Disaster zones (medium) polled third
- Ensures most important locations get fresh data first

---

### 3. Batch API Optimization

**Before:**
```python
# ❌ One API call per location
for location in due_locations:
    hourly_response = await self.get(url, params_for_single_location)
    daily_response = await self.get(url, params_for_single_location)
    # 2 API calls per location × 15 locations = 30 API calls
```

**After:**
```python
# ✅ Up to 10 locations per API call
batches = [
    due_locations[i:i + 10]
    for i in range(0, len(due_locations), 10)
]

for batch in batches:
    # Single API call for all locations in batch
    response = await self.get(url, batch_params)
    # 15 locations = 2 batches = 2 API calls (15x reduction!)
```

**Open-Meteo Batch API Format:**
```python
{
    "latitude": "31.5497,24.8607,33.6844",  # Comma-separated
    "longitude": "74.3436,67.0011,73.0479", # Comma-separated
    "hourly": "temperature_2m,precipitation,...",
    "daily": "temperature_2m_max,precipitation_sum,...",
    "timezone": "Asia/Karachi",
    "forecast_days": 5
}
```

**Response Structure:**
```json
[
  {
    "latitude": 31.5497,
    "longitude": 74.3436,
    "hourly": { "time": [...], "temperature_2m": [...] },
    "daily": { "time": [...], "temperature_2m_max": [...] }
  },
  {
    "latitude": 24.8607,
    "longitude": 67.0011,
    "hourly": { "time": [...], "temperature_2m": [...] },
    "daily": { "time": [...], "temperature_2m_max": [...] }
  },
  ...
]
```

**Impact:**
- **15 locations:** 30 API calls → 2 API calls (15x reduction)
- **270 locations (future):** 540 API calls → 54 API calls (10x reduction)
- Well within Open-Meteo free tier (10 requests/minute)
- Faster collection cycles (7.5 seconds for 15 locations)

---

### 4. Poll State Tracking

**After each collection attempt:**

```python
await self._update_poll_state(
    location=location,
    success=True,  # or False
    poll_time=datetime.now(_PKT),
)
```

**Database Update:**
```sql
UPDATE pakistan_locations
SET
    last_polled_at = $2,                    -- When we polled
    last_poll_outcome = $3::poll_outcome,   -- 'success' or 'failed'
    next_poll_due_at = $4,                  -- poll_time + poll_interval_minutes
    consecutive_failures = CASE
        WHEN $5 = TRUE THEN 0               -- Reset on success
        ELSE consecutive_failures + 1       -- Increment on failure
    END,
    updated_at = now()
WHERE location_id = $1
```

**Impact:**
- Scheduler knows when each location was last polled
- Automatic retry scheduling for failed locations
- Tracks consecutive failures for alerting
- Enables per-location polling intervals (3-6 hours)

---

## API Call Comparison

### Scenario: 15 Locations, 3-hour polling interval

**Old Implementation (Individual Calls):**
```
Every 15 minutes:
  - Check: Should we poll? → YES (always polls all)
  - API calls: 15 locations × 2 calls (hourly + daily) = 30 calls
  - Time: 15 × 500ms delay = 7.5 seconds
  - Per hour: 4 cycles × 30 calls = 120 API calls
  - Per day: 120 × 24 = 2,880 API calls
```

**New Implementation (Batch + Smart Polling):**
```
Every 15 minutes:
  - Check: Should we poll? → Only if next_poll_due_at <= now
  - Locations due: 15 ÷ 12 (3-hour interval) = ~1-2 locations per check
  - API calls: 1 batch call = 1 API call
  - Time: 1 × 500ms = 0.5 seconds
  - Per hour: 4 cycles × 1 call = 4 API calls
  - Per day: 4 × 24 = 96 API calls
```

**Reduction: 2,880 → 96 API calls per day (30x reduction!)**

---

## Code Flow

### 1. Collector Initialization
```python
collector = OpenMeteoCollector(
    http_client=client,
    reference_repo=ref_repo,
    cycle_repo=cycle_repo,
    openmeteo_service=service,
    pakistan_locations=locations,  # Loaded from database with poll state
)
```

### 2. Collection Cycle
```python
async def collect():
    # 1. Get locations due for polling
    due_locations = get_due_locations()  # Checks next_poll_due_at
    
    # 2. Split into batches of 10
    batches = [due_locations[i:i+10] for i in range(0, len(due_locations), 10)]
    
    # 3. Process each batch
    for batch in batches:
        # Single API call for all locations in batch
        batch_stats = await collect_batch(batch, cycle_id)
        
        # 500ms delay between batches
        await rate_limit_delay(500)
```

### 3. Batch Collection
```python
async def collect_batch(locations, cycle_id):
    # 1. Build batch params (comma-separated lat/lon)
    batch_params = service.build_batch_params(locations)
    
    # 2. Single API call
    response = await get(url, params=batch_params)
    batch_data = response.json()
    
    # 3. Process each location's data
    for i, location in enumerate(locations):
        location_data = extract_location_data(batch_data, i)
        
        # Parse, check breaches, UPSERT
        hourly_records = service.parse_hourly(location_data, location)
        daily_summaries = service.parse_daily(location_data, location)
        await service.process_location(hourly_records, daily_summaries, cycle_id)
        
        # Update poll state
        await update_poll_state(location, success=True, poll_time=now())
```

---

## Configuration

### Environment Variables
```bash
# Open-Meteo settings
OPENMETEO_BASE_URL=https://api.open-meteo.com/v1/forecast
OPENMETEO_POLL_INTERVAL_MINUTES=15  # Scheduler check frequency
OPENMETEO_REQUEST_DELAY_MS=500      # Delay between batches
```

### Location Configuration (Database)
```sql
-- Example: Lahore (Provincial Capital)
INSERT INTO pakistan_locations (
    location_name,
    province,
    latitude,
    longitude,
    poll_priority,           -- 'critical' for provincial capitals
    poll_interval_minutes,   -- 180 (3 hours)
    next_poll_due_at,        -- NULL (poll immediately on first run)
    is_active
) VALUES (
    'Lahore',
    'punjab',
    31.5497,
    74.3436,
    'critical',
    180,
    NULL,
    TRUE
);
```

---

## Testing

### Test 1: Due Location Filtering
```python
# Setup: 3 locations with different next_poll_due_at
locations = [
    Location(name="A", next_poll_due_at=now - 1 hour),  # Due
    Location(name="B", next_poll_due_at=now + 1 hour),  # Not due
    Location(name="C", next_poll_due_at=None),          # Due (never polled)
]

due = collector.get_due_locations()
assert len(due) == 2  # Only A and C
assert due[0].name == "A"
assert due[1].name == "C"
```

### Test 2: Priority Sorting
```python
locations = [
    Location(name="Low", poll_priority="low"),
    Location(name="Critical", poll_priority="critical"),
    Location(name="High", poll_priority="high"),
]

due = collector.get_due_locations()
assert due[0].name == "Critical"
assert due[1].name == "High"
assert due[2].name == "Low"
```

### Test 3: Batch API Call
```python
# 15 locations should result in 2 batches
locations = [Location(f"Loc{i}") for i in range(15)]

batches = [locations[i:i+10] for i in range(0, len(locations), 10)]
assert len(batches) == 2
assert len(batches[0]) == 10
assert len(batches[1]) == 5
```

### Test 4: Poll State Update
```python
await collector._update_poll_state(
    location=lahore,
    success=True,
    poll_time=datetime(2025, 7, 15, 9, 0, 0, tzinfo=PKT),
)

# Verify database update
updated = await ref_repo.get_location_by_id(lahore.location_id)
assert updated.last_polled_at == datetime(2025, 7, 15, 9, 0, 0, tzinfo=PKT)
assert updated.last_poll_outcome == "success"
assert updated.next_poll_due_at == datetime(2025, 7, 15, 12, 0, 0, tzinfo=PKT)  # +3 hours
assert updated.consecutive_failures == 0
```

---

## Monitoring

### Cycle Logs
```
2025-07-15 09:00:00 [INFO] Starting Open-Meteo collection cycle: abc-123
2025-07-15 09:00:00 [INFO] Found 3 locations due for polling (out of 15 total active)
2025-07-15 09:00:00 [INFO] Polling 3 locations in 1 batch(es) of up to 10 locations each
2025-07-15 09:00:01 [DEBUG] Processing batch 1/1 with 3 locations
2025-07-15 09:00:02 [DEBUG] Processed Lahore: 120 hourly, 5 daily, 1 breaches
2025-07-15 09:00:02 [DEBUG] Updated poll state for Lahore: outcome=success, next_due=2025-07-15 12:00:00 PKT
2025-07-15 09:00:02 [INFO] Open-Meteo cycle abc-123 completed: status=completed, locations=3/3, hourly=360, daily=15, breaches=1, API_calls=1
```

### Health Dashboard Query
```sql
SELECT
    location_name,
    last_polled_at,
    last_poll_outcome,
    next_poll_due_at,
    consecutive_failures,
    EXTRACT(EPOCH FROM (now() - last_polled_at)) / 60 AS minutes_since_poll
FROM pakistan_locations
WHERE is_active = TRUE
ORDER BY next_poll_due_at ASC NULLS FIRST;
```

---

## Benefits Summary

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| API calls per day (15 locations) | 2,880 | 96 | **30x reduction** |
| API calls per cycle | 30 | 1-2 | **15-30x reduction** |
| Cycle time | 7.5s | 0.5-1s | **7-15x faster** |
| Rate limit risk | High | Very Low | **Safe** |
| Poll frequency | Every 15 min | Every 3-6 hours | **Configurable** |
| Priority support | No | Yes | **Critical first** |
| Poll state tracking | No | Yes | **Full audit trail** |

---

## Future Enhancements

1. **Adaptive polling intervals** - Increase frequency during active disasters
2. **Location grouping** - Group nearby locations for better batch efficiency
3. **Failure retry logic** - Exponential backoff for failed locations
4. **Health monitoring** - Alert when consecutive_failures > threshold
5. **Performance metrics** - Track batch processing time per location

---

## References

- [Open-Meteo API Documentation](https://open-meteo.com/en/docs)
- [Open-Meteo Batch Requests](https://open-meteo.com/en/docs#api-documentation)
- Project Overview: Section 5.2 - Open-Meteo Weather API
- Database Schema: pakistan_locations table definition


1	Check next_poll_due_at before polling	❌ Not Implemented	Polls all locations every time → excessive API calls  

2	Sort locations by poll_priority	❌ Not Implemented	Critical locations not polled first  

3	Update poll state after collection	❌ Not Implemented	No tracking of when location was last polled  

4	Detect breaches for 7 disaster types	❌ Only 1/7 Implemented	Only heatwave alerts generated, missing 6 disaster types  

5	Set all 9 weather flags	❌ 7/9 Implemented	Dust storm and fog not flagged  

6	Populate all hourly table fields	❌ 2 fields missing	coordinates and data_freshness_minutes not set  

7	Populate all daily table fields