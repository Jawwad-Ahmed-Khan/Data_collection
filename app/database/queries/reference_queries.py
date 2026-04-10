"""
ClimaSync Collection Service — Reference Data Queries
"""

GET_API_REGISTRY = """
    SELECT
        api_id,
        api_name,
        display_name,
        base_url,
        max_requests_per_minute,
        is_active,
        current_health,
        consecutive_failures,
        backoff_until,
        last_success_at,
        last_failure_at,
        avg_latency_ms
    FROM api_registry
    WHERE is_active = TRUE
"""

GET_API_BY_NAME = """
    SELECT
        api_id,
        api_name,
        display_name,
        base_url,
        max_requests_per_minute,
        is_active,
        current_health,
        consecutive_failures,
        backoff_until,
        last_success_at,
        last_failure_at,
        avg_latency_ms
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
        threshold_id,
        disaster_kind,
        metric_name,
        province,
        district,
        unit,
        breach_direction,
        watch_threshold,
        warning_threshold,
        emergency_threshold,
        extreme_threshold,
        applies_season,
        description
    FROM disaster_thresholds
    WHERE is_active = TRUE
"""

GET_ACTIVE_LOCATIONS = """
    SELECT
        location_id,
        location_key,
        location_name,
        district,
        province,
        latitude,
        longitude,
        population,
        flood_risk_zone,
        seismic_zone,
        heat_risk_zone
    FROM pakistan_locations
    WHERE is_active = TRUE
"""
