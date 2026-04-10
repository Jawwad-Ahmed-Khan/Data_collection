"""
ClimaSync Collection Service — Flood SQL Queries
"""

UPSERT_FLOOD_CURRENT = """
    INSERT INTO flood_gauge_current (
        gauge_id,
        google_gauge_id,
        gauge_name,
        river_name,
        river_system,
        district,
        province,
        reading_time,
        current_level_m,
        warning_level_m,
        danger_level_m,
        extreme_level_m,
        pct_of_warning,
        pct_of_danger,
        pct_of_historical_max,
        previous_level_m,
        level_change_m,
        rise_rate_m_per_hour,
        river_trend,
        hours_to_warning,
        hours_to_danger,
        flood_status,
        has_breach,
        breach_severity
    ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, 
        $11, $12, $13, $14, $15, $16, $17, $18, 
        $19, $20, $21, $22, $23, $24
    )
    ON CONFLICT (gauge_id) DO UPDATE SET
        reading_time = EXCLUDED.reading_time,
        current_level_m = EXCLUDED.current_level_m,
        pct_of_warning = EXCLUDED.pct_of_warning,
        pct_of_danger = EXCLUDED.pct_of_danger,
        pct_of_historical_max = EXCLUDED.pct_of_historical_max,
        previous_level_m = EXCLUDED.previous_level_m,
        level_change_m = EXCLUDED.level_change_m,
        rise_rate_m_per_hour = EXCLUDED.rise_rate_m_per_hour,
        river_trend = EXCLUDED.river_trend,
        hours_to_warning = EXCLUDED.hours_to_warning,
        hours_to_danger = EXCLUDED.hours_to_danger,
        flood_status = EXCLUDED.flood_status,
        has_breach = EXCLUDED.has_breach,
        breach_severity = EXCLUDED.breach_severity
"""

UPSERT_FLOOD_FORECAST = """
    INSERT INTO flood_gauge_forecasts (
        gauge_id,
        google_gauge_id,
        forecast_for_datetime,
        forecast_date,
        day_offset,
        forecast_horizon_h,
        level_p10_m,
        level_p50_m,
        level_p90_m,
        prob_exceeds_warning_pct,
        prob_exceeds_danger_pct,
        forecast_status,
        worst_case_status,
        has_breach,
        breach_severity
    ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, 
        $10, $11, $12, $13, $14, $15
    )
    ON CONFLICT (gauge_id, forecast_for_datetime) DO UPDATE SET
        level_p10_m = EXCLUDED.level_p10_m,
        level_p50_m = EXCLUDED.level_p50_m,
        level_p90_m = EXCLUDED.level_p90_m,
        prob_exceeds_warning_pct = EXCLUDED.prob_exceeds_warning_pct,
        prob_exceeds_danger_pct = EXCLUDED.prob_exceeds_danger_pct,
        forecast_status = EXCLUDED.forecast_status,
        worst_case_status = EXCLUDED.worst_case_status,
        has_breach = EXCLUDED.has_breach,
        breach_severity = EXCLUDED.breach_severity,
        last_updated_at = now()
"""

GET_ACTIVE_FLOOD_GAUGES = """
    SELECT
        gauge_id,
        google_gauge_id,
        gauge_name,
        river_name,
        river_system,
        district,
        province,
        latitude,
        longitude,
        historical_max_m,
        bankfull_level_m,
        basin_name,
        upstream_area_sqkm,
        nearest_location_id,
        poll_priority
    FROM flood_gauge_registry
    WHERE is_active = TRUE
"""

GET_PREVIOUS_READING = """
    SELECT
        gauge_id,
        google_gauge_id,
        gauge_name,
        river_name,
        river_system,
        district,
        province,
        reading_time,
        current_level_m,
        warning_level_m,
        danger_level_m,
        extreme_level_m,
        pct_of_warning,
        pct_of_danger,
        pct_of_historical_max,
        previous_level_m,
        level_change_m,
        rise_rate_m_per_hour,
        river_trend,
        hours_to_warning,
        hours_to_danger,
        flood_status,
        has_breach,
        breach_severity
    FROM flood_gauge_current
    WHERE gauge_id = $1
"""
