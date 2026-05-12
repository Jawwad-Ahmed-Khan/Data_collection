"""
ClimaSync Collection Service — Reference Data Queries
"""

GET_API_REGISTRY = """
    SELECT
        api_id, api_name, display_name, base_url, documentation_url,
        max_requests_per_minute, max_requests_per_day,
        is_active, current_health, consecutive_failures,
        backoff_until, last_success_at, last_failure_at, avg_latency_ms
    FROM api_registry
    WHERE is_active = TRUE
"""

GET_API_BY_NAME = """
    SELECT
        api_id, api_name, display_name, base_url, documentation_url,
        max_requests_per_minute, max_requests_per_day,
        is_active, current_health, consecutive_failures,
        backoff_until, last_success_at, last_failure_at, avg_latency_ms
    FROM api_registry
    WHERE api_name = $1 AND is_active = TRUE
"""

UPDATE_API_BACKOFF = """
    UPDATE api_registry
    SET backoff_until = $2,
        current_health = 'rate_limited',
        consecutive_failures = consecutive_failures + 1,
        updated_at = now()
    WHERE api_name = $1
"""

GET_ALL_THRESHOLDS = """
    SELECT
        threshold_id, disaster_kind, metric_name, province, district,
        applies_season, unit, breach_direction,
        watch_threshold, warning_threshold, emergency_threshold, extreme_threshold,
        description, is_active
    FROM disaster_thresholds
    WHERE is_active = TRUE
"""

GET_ACTIVE_LOCATIONS = """
    SELECT
        location_id, location_key, location_name, local_name, location_tier,
        district, division, province, latitude, longitude, elevation_m,
        population, population_density, flood_risk_zone, seismic_zone,
        heat_risk_zone, drought_risk_zone, infrastructure_quality,
        drainage_quality, building_stock, poll_priority, poll_interval_minutes,
        last_polled_at, last_poll_outcome, next_poll_due_at, consecutive_failures,
        is_active, data_source
    FROM pakistan_locations
    WHERE is_active = TRUE
"""

GET_DUE_LOCATIONS = """
    SELECT
        location_id, location_key, location_name, local_name, location_tier,
        district, division, province, latitude, longitude, elevation_m,
        population, population_density, flood_risk_zone, seismic_zone,
        heat_risk_zone, drought_risk_zone, infrastructure_quality,
        drainage_quality, building_stock, poll_priority, poll_interval_minutes,
        last_polled_at, last_poll_outcome, next_poll_due_at, consecutive_failures,
        is_active, data_source
    FROM pakistan_locations
    WHERE is_active = TRUE
    AND (next_poll_due_at IS NULL OR next_poll_due_at <= now())
    ORDER BY
        CASE poll_priority WHEN 'critical' THEN 1
                           WHEN 'high'     THEN 2
                           WHEN 'medium'   THEN 3
                           WHEN 'low'      THEN 4 END,
        next_poll_due_at ASC NULLS FIRST
"""

UPDATE_LOCATION_POLL_STATE = """
    UPDATE pakistan_locations
    SET
        last_polled_at = $2,
        last_poll_outcome = $3::poll_outcome,
        next_poll_due_at = CASE WHEN $5 = TRUE THEN $4 ELSE next_poll_due_at END,
        consecutive_failures = CASE
            WHEN $5 = TRUE THEN 0
            ELSE consecutive_failures + 1
        END,
        updated_at = now()
    WHERE location_id = $1
"""

GET_NEAREST_LOCATION = """
    SELECT
        location_id, location_key, location_name, local_name, location_tier,
        district, division, province, latitude, longitude, elevation_m,
        population, population_density, flood_risk_zone, seismic_zone,
        heat_risk_zone, drought_risk_zone, infrastructure_quality,
        drainage_quality, building_stock, poll_priority, poll_interval_minutes,
        last_polled_at, last_poll_outcome, next_poll_due_at, consecutive_failures,
        is_active, data_source
    FROM pakistan_locations
    WHERE is_active = TRUE
    ORDER BY coordinates <-> ST_SetSRID(ST_MakePoint($1, $2), 4326)
    LIMIT 1
"""
