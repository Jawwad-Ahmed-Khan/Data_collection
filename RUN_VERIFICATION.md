# 🚀 Run Verification - Quick Commands

## Verify Both Problems Are Solved

### Option 1: Quick Verification Script (Recommended)

```bash
python verify_poll_state.py
```

**What it tests:**
- ✅ Priority sorting (critical → high → medium → low)
- ✅ Database connection to Supabase
- ✅ Poll state updates saved to database
- ✅ Consecutive failures tracking
- ✅ Next poll time calculation

**Expected output:**
```
✅ TEST 1 PASSED: Priority sorting works correctly!
✅ TEST 2 PASSED: Database updates work correctly!

🎉 ALL TESTS PASSED!

✅ PROBLEM 2 SOLVED: Priority sorting works correctly
✅ PROBLEM 3 SOLVED: Poll state is saved to Supabase
```

---

### Option 2: Pytest Tests

```bash
# Run all tests
pytest tests/test_openmeteo_poll_state.py -v

# Run specific test
pytest tests/test_openmeteo_poll_state.py::test_priority_sorting -v
pytest tests/test_openmeteo_poll_state.py::test_poll_state_update_database -v
```

---

### Option 3: Manual Database Check

```bash
# Connect to Supabase and run these queries
```

**Query 1: Check if poll_priority exists**
```sql
SELECT
    location_name,
    poll_priority,
    poll_interval_minutes
FROM pakistan_locations
WHERE is_active = TRUE
LIMIT 5;
```

**Query 2: Check if poll state fields exist**
```sql
SELECT
    location_name,
    last_polled_at,
    last_poll_outcome,
    next_poll_due_at,
    consecutive_failures
FROM pakistan_locations
WHERE is_active = TRUE
LIMIT 5;
```

**Query 3: Manually update a location and verify**
```sql
-- Update poll state
UPDATE pakistan_locations
SET
    last_polled_at = now(),
    last_poll_outcome = 'success',
    next_poll_due_at = now() + INTERVAL '3 hours',
    consecutive_failures = 0
WHERE location_name = 'Lahore';

-- Verify update
SELECT
    location_name,
    last_polled_at,
    last_poll_outcome,
    next_poll_due_at,
    consecutive_failures
FROM pakistan_locations
WHERE location_name = 'Lahore';
```

---

## Troubleshooting

### Error: "Database connection failed"

**Solution:**
1. Check `.env` file has correct Supabase credentials:
   ```bash
   COLLECTION_DB_HOST=your-project.supabase.co
   COLLECTION_DB_PASSWORD=your-password
   ```

2. Verify Supabase project is running

3. Check network connection

### Error: "Column 'poll_priority' does not exist"

**Solution:**
The `pakistan_locations` table needs these columns. Run this migration:

```sql
-- Add missing columns if they don't exist
ALTER TABLE pakistan_locations
ADD COLUMN IF NOT EXISTS poll_priority VARCHAR(20) DEFAULT 'medium',
ADD COLUMN IF NOT EXISTS poll_interval_minutes INT DEFAULT 180,
ADD COLUMN IF NOT EXISTS last_polled_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS last_poll_outcome VARCHAR(20),
ADD COLUMN IF NOT EXISTS next_poll_due_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS consecutive_failures INT DEFAULT 0;

-- Create enum type if it doesn't exist
DO $$ BEGIN
    CREATE TYPE poll_priority AS ENUM ('critical', 'high', 'medium', 'low');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Update column to use enum
ALTER TABLE pakistan_locations
ALTER COLUMN poll_priority TYPE poll_priority USING poll_priority::poll_priority;
```

### Error: "UPDATE_LOCATION_POLL_STATE not found"

**Solution:**
The query is defined in `app/database/queries/reference_queries.py`. Make sure the file is saved and imported correctly.

---

## Quick Verification Checklist

Run these commands in order:

```bash
# 1. Check files exist
ls -la app/collectors/openmeteo_collector.py
ls -la app/repositories/reference_repository.py
ls -la app/database/queries/reference_queries.py

# 2. Check implementation exists
grep -n "poll_priority" app/collectors/openmeteo_collector.py
grep -n "update_location_poll_state" app/repositories/reference_repository.py
grep -n "UPDATE_LOCATION_POLL_STATE" app/database/queries/reference_queries.py

# 3. Run verification
python verify_poll_state.py

# 4. If all pass, you're done! ✅
```

---

## Expected Results

### ✅ Success Output

```
====================================================================
POLL STATE MANAGEMENT VERIFICATION
====================================================================

This script verifies that:
1. ✓ Priority sorting is implemented
2. ✓ Poll state updates are saved to Supabase
====================================================================

====================================================================
TEST 1: PRIORITY SORTING
====================================================================

📋 Locations after sorting:
   1. Critical Priority City (priority: critical)
   2. High Priority City (priority: high)
   3. Medium Priority City (priority: medium)
   4. Low Priority City (priority: low)

✅ TEST 1 PASSED: Priority sorting works correctly!
   Order: critical → high → medium → low

====================================================================
TEST 2: DATABASE UPDATE
====================================================================

🔌 Connecting to Supabase...
✅ Connected to Supabase

📝 Creating test location: <uuid>
✅ Test location created in database

🔄 Updating poll state...
   last_polled_at: 2025-07-15 09:00:00 PKT
   next_poll_due_at: 2025-07-15 12:00:00 PKT
✅ Poll state update executed

🔍 Verifying data in Supabase...

📊 Data retrieved from Supabase:
   location_name: Test Verification Location
   last_polled_at: 2025-07-15 09:00:00+05:00
   last_poll_outcome: success
   next_poll_due_at: 2025-07-15 12:00:00+05:00
   consecutive_failures: 0
   poll_priority: critical
   poll_interval_minutes: 180

✅ Interval calculation correct: 180.0 minutes

🔄 Testing consecutive failures tracking...
   After 2 failures: consecutive_failures = 2
   After success: consecutive_failures = 0

✅ Consecutive failures tracking works correctly!

🧹 Cleaning up test data...
✅ Test data cleaned up
✅ Disconnected from Supabase

✅ TEST 2 PASSED: Database updates work correctly!
   ✓ Poll state saved to Supabase
   ✓ Timestamps calculated correctly
   ✓ Consecutive failures tracked

====================================================================
VERIFICATION SUMMARY
====================================================================

Test 1 (Priority Sorting):  ✅ PASSED
Test 2 (Database Update):   ✅ PASSED

🎉 ALL TESTS PASSED!

✅ PROBLEM 2 SOLVED: Priority sorting works correctly
✅ PROBLEM 3 SOLVED: Poll state is saved to Supabase

The implementation is working correctly! 🚀
====================================================================
```

---

## Next Steps After Verification

Once verification passes:

1. **Configure your locations:**
   ```sql
   UPDATE pakistan_locations
   SET
       poll_priority = 'critical',
       poll_interval_minutes = 180
   WHERE location_name IN ('Lahore', 'Karachi', 'Islamabad');
   ```

2. **Run the collector:**
   ```bash
   python -m app.main
   ```

3. **Monitor logs:**
   ```bash
   tail -f logs/collection.log | grep "Found.*locations due"
   ```

4. **Check database:**
   ```sql
   SELECT location_name, last_polled_at, next_poll_due_at
   FROM pakistan_locations
   WHERE last_polled_at IS NOT NULL
   ORDER BY last_polled_at DESC;
   ```

---

## Support

If verification fails:
1. Check error message in output
2. Verify Supabase connection
3. Check database schema matches requirements
4. Review `VERIFICATION_COMPLETE.md` for detailed implementation
5. Check `IMPLEMENTATION_SUMMARY.md` for code changes

**Both problems are solved and ready to use!** ✅
