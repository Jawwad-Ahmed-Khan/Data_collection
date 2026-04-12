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
    SET backoff_until = $2
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
