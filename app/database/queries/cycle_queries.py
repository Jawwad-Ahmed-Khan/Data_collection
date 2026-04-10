"""
ClimaSync Collection Service — Cycle SQL Queries
"""

INSERT_CYCLE = """
    INSERT INTO collection_cycles (
        api_id,
        api_name,
        status,
        started_at,
        locations_targeted,
        locations_success,
        locations_failed,
        rows_upserted,
        rows_inserted,
        breaches_triggered,
        rate_limit_hits
    ) VALUES (
        $1, $2, 'running', now(), 0, 0, 0, 0, 0, 0, 0
    )
    RETURNING cycle_id
"""

UPDATE_CYCLE = """
    UPDATE collection_cycles
    SET status = $2,
        completed_at = now(),
        duration_ms = EXTRACT(EPOCH FROM (now() - started_at)) * 1000,
        locations_targeted = $3,
        locations_success = $4,
        locations_failed = $5,
        rows_upserted = $6,
        rows_inserted = $7,
        breaches_triggered = $8,
        rate_limit_hits = $9
    WHERE cycle_id = $1
"""

GET_MOST_RECENT_CYCLE = """
    SELECT *
    FROM collection_cycles
    WHERE api_id = $1
    ORDER BY started_at DESC
    LIMIT 1
"""
