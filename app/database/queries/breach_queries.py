"""
ClimaSync Collection Service — Breach SQL Queries
"""

INSERT_BREACH_LOG = """
    INSERT INTO threshold_breach_log (
        source_api,
        threshold_id,
        weather_location_id,
        seismic_event_id,
        gauge_id,
        disaster_kind,
        metric_name,
        location_name,
        district,
        province,
        latitude,
        longitude,
        coordinates,
        observed_value,
        threshold_value,
        breach_severity,
        excess_amount,
        excess_pct,
        observation_time,
        is_forecast_breach,
        forecast_horizon_h,
        is_duplicate,
        duplicate_of_breach_id,
        dispatch_status,
        suppression_window_used_m
    ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
        ST_SetSRID(ST_MakePoint($12, $11), 4326),
        $13, $14, $15, $16, $17, $18, $19, $20, $21, $22,
        CASE WHEN $21 = TRUE THEN 'suppressed'::breach_dispatch_status ELSE 'pending'::breach_dispatch_status END,
        $23
    )
    RETURNING breach_id
"""

MARK_BREACH_DISPATCHED = """
    UPDATE threshold_breach_log
    SET dispatch_status = 'dispatched',
        dispatched_at = now(),
        main_system_alert_id = $2,
        dispatch_attempt_count = dispatch_attempt_count + 1
    WHERE breach_id = $1
"""

MARK_BREACH_FAILED = """
    UPDATE threshold_breach_log
    SET dispatch_status = 'dispatch_failed',
        last_dispatch_error = $2,
        dispatch_attempt_count = dispatch_attempt_count + 1
    WHERE breach_id = $1
"""

FIND_RECENT_BREACH = """
    SELECT breach_id
    FROM threshold_breach_log
    WHERE metric_name = $1
      AND detected_at >= $2
      AND is_duplicate = FALSE
      AND ($3::uuid IS NULL OR weather_location_id = $3 OR gauge_id = $3)
      AND is_forecast_breach = $4::boolean
      AND ($5::text IS NULL OR breach_severity = $5::breach_level)
    ORDER BY detected_at DESC
    LIMIT 1
"""

FIND_RECENT_SEISMIC_BREACH = """
    SELECT breach_id
    FROM threshold_breach_log
    WHERE seismic_event_id = $1
      AND breach_severity = $2::breach_level
      AND is_duplicate = FALSE
    ORDER BY detected_at DESC
    LIMIT 1
"""

GET_UNDISPATCHED_BREACHES = """
    SELECT
        breach_id,
        source_api,
        disaster_kind,
        metric_name,
        location_name,
        district,
        province,
        latitude,
        longitude,
        observed_value,
        threshold_value,
        breach_severity,
        observation_time,
        is_forecast_breach,
        forecast_horizon_h,
        detected_at,
        dispatch_attempt_count
    FROM threshold_breach_log
    WHERE dispatch_status = 'pending'
      AND is_duplicate = FALSE
      AND dispatch_attempt_count < $1
    ORDER BY detected_at ASC
    LIMIT $2
"""
