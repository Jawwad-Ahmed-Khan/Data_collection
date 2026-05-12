"""
ClimaSync Collection Service — Flood PostgreSQL Queries
"""

UPSERT_FLOOD_GAUGE_REGISTRY = """
    INSERT INTO flood_gauge_registry (
        gauge_id, google_gauge_id, gauge_name, river_name, district, province,
        latitude, longitude, bankfull_level_m, warning_level_m, danger_level_m, extreme_level_m
    ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
    )
    ON CONFLICT (google_gauge_id) DO UPDATE SET
        gauge_name = EXCLUDED.gauge_name,
        river_name = EXCLUDED.river_name,
        district = EXCLUDED.district,
        province = EXCLUDED.province,
        latitude = EXCLUDED.latitude,
        longitude = EXCLUDED.longitude,
        bankfull_level_m = EXCLUDED.bankfull_level_m,
        warning_level_m = EXCLUDED.warning_level_m,
        danger_level_m = EXCLUDED.danger_level_m,
        extreme_level_m = EXCLUDED.extreme_level_m,
        updated_at = now()
    RETURNING gauge_id
"""

UPSERT_FLOOD_CURRENT = """
    INSERT INTO flood_gauge_current (
        gauge_id, google_gauge_id, gauge_name, river_name, river_system,
        district, province, cycle_id,
        reading_time, current_level_m,
        warning_level_m, danger_level_m, extreme_level_m,
        pct_of_warning, pct_of_danger, pct_of_historical_max,
        previous_level_m, level_change_m, rise_rate_m_per_hour,
        river_trend, hours_to_warning, hours_to_danger,
        flood_status, has_breach, breach_severity, threshold_id,
        raw_api_response, collected_at
    ) VALUES (
        $1::uuid, $2, $3, $4, $5, $6, $7, $8::uuid, $9, $10,
        $11, $12, $13, $14, $15, $16, $17, $18, $19,
        $20::river_trend, $21, $22, $23::flood_status, $24, $25::breach_level, $26::uuid,
        $27::jsonb, $28
    )
    ON CONFLICT (gauge_id) DO UPDATE SET
        reading_time = EXCLUDED.reading_time,
        current_level_m = EXCLUDED.current_level_m,
        warning_level_m = EXCLUDED.warning_level_m,
        danger_level_m = EXCLUDED.danger_level_m,
        extreme_level_m = EXCLUDED.extreme_level_m,
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
        breach_severity = EXCLUDED.breach_severity,
        threshold_id = EXCLUDED.threshold_id,
        raw_api_response = EXCLUDED.raw_api_response,
        collected_at = EXCLUDED.collected_at,
        cycle_id = EXCLUDED.cycle_id
    RETURNING gauge_id, (xmax = 0) AS was_inserted
"""

UPSERT_FLOOD_FORECAST = """
    INSERT INTO flood_gauge_forecasts (
        gauge_id, google_gauge_id, gauge_name, river_name, district, province,
        forecast_for_datetime, forecast_issued_at,
        level_p10_m, level_p50_m, level_p90_m,
        prob_exceeds_warning_pct, prob_exceeds_danger_pct, prob_exceeds_extreme_pct,
        forecast_status, worst_case_status, has_forecast_breach, breach_severity, raw_api_response
    ) VALUES (
        $1::uuid, $2, $3, $4, $5, $6, $7, $8,
        $9, $10, $11, $12, $13, $14, $15::flood_status, $16::flood_status, $17, $18::breach_level, $19::jsonb
    )
    ON CONFLICT (gauge_id, forecast_for_datetime) DO UPDATE SET
        level_p10_m = EXCLUDED.level_p10_m,
        level_p50_m = EXCLUDED.level_p50_m,
        level_p90_m = EXCLUDED.level_p90_m,
        prob_exceeds_warning_pct = EXCLUDED.prob_exceeds_warning_pct,
        prob_exceeds_danger_pct = EXCLUDED.prob_exceeds_danger_pct,
        prob_exceeds_extreme_pct = EXCLUDED.prob_exceeds_extreme_pct,
        forecast_status = EXCLUDED.forecast_status,
        worst_case_status = EXCLUDED.worst_case_status,
        has_forecast_breach = EXCLUDED.has_forecast_breach,
        breach_severity = EXCLUDED.breach_severity,
        raw_api_response = EXCLUDED.raw_api_response,
        gauge_name = EXCLUDED.gauge_name,
        river_name = EXCLUDED.river_name,
        district = EXCLUDED.district,
        province = EXCLUDED.province,
        forecast_issued_at = EXCLUDED.forecast_issued_at,
        last_updated_at = now()
"""

GET_ACTIVE_FLOOD_GAUGES = """
    SELECT *
    FROM flood_gauge_registry
"""

GET_PREVIOUS_READING = """
    SELECT *
    FROM flood_gauge_current
    WHERE gauge_id = $1::uuid
    ORDER BY reading_time DESC
    LIMIT 1
"""
