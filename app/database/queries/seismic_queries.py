"""
ClimaSync Collection Service — Seismic PostgreSQL Queries

Contains ONLY SQL query strings. No imports to avoid circular dependencies.
"""

UPSERT_SEISMIC_EVENT = """
    INSERT INTO seismic_events (
        event_id, usgs_event_id, usgs_event_url, cycle_id, magnitude, 
        magnitude_type, coordinates, latitude, longitude, depth_km, 
        usgs_place, resolved_district, resolved_province, nearest_location_id, 
        distance_to_nearest_km, felt_reports, cdi, mmi, tsunami_flag, 
        usgs_alert_level, significance, station_count, azimuthal_gap_deg, 
        rms_seconds, data_quality, contributing_networks, has_breach, 
        breach_severity, threshold_id, usgs_last_updated_at, earthquake_time, 
        raw_api_response
    ) VALUES (
        $1, $2, $3, $4, $5, 
        $6, ST_SetSRID(ST_MakePoint($8::float8, $7::float8), 4326), $7::float8, $8::float8, $9, 
        $10, $11, $12, $13, 
        $14, $15, $16, $17, $18, 
        $19, $20, $21, $22, 
        $23, $24, $25, $26, 
        $27, $28, $29, $30, 
        $31
    )
    ON CONFLICT (usgs_event_id) DO UPDATE SET
        cycle_id = EXCLUDED.cycle_id,
        magnitude = EXCLUDED.magnitude,
        magnitude_type = EXCLUDED.magnitude_type,
        coordinates = EXCLUDED.coordinates,
        latitude = EXCLUDED.latitude,
        longitude = EXCLUDED.longitude,
        depth_km = EXCLUDED.depth_km,
        usgs_place = EXCLUDED.usgs_place,
        resolved_district = EXCLUDED.resolved_district,
        resolved_province = EXCLUDED.resolved_province,
        nearest_location_id = EXCLUDED.nearest_location_id,
        distance_to_nearest_km = EXCLUDED.distance_to_nearest_km,
        felt_reports = EXCLUDED.felt_reports,
        cdi = EXCLUDED.cdi,
        mmi = EXCLUDED.mmi,
        tsunami_flag = EXCLUDED.tsunami_flag,
        usgs_alert_level = EXCLUDED.usgs_alert_level,
        significance = EXCLUDED.significance,
        station_count = EXCLUDED.station_count,
        azimuthal_gap_deg = EXCLUDED.azimuthal_gap_deg,
        rms_seconds = EXCLUDED.rms_seconds,
        data_quality = EXCLUDED.data_quality,
        contributing_networks = EXCLUDED.contributing_networks,
        has_breach = EXCLUDED.has_breach,
        breach_severity = EXCLUDED.breach_severity,
        threshold_id = EXCLUDED.threshold_id,
        usgs_last_updated_at = EXCLUDED.usgs_last_updated_at,
        earthquake_time = EXCLUDED.earthquake_time,
        raw_api_response = EXCLUDED.raw_api_response,
        updated_at = now()
    RETURNING event_id, (xmax = 0) AS was_inserted
"""

GET_RECENT_SEISMIC_EVENTS = """
    SELECT *
    FROM seismic_events
    WHERE earthquake_time >= now() - interval '24 hours'
    ORDER BY earthquake_time DESC
"""

DELETE_OLD_SEISMIC_EVENTS = """
    DELETE FROM seismic_events
    WHERE earthquake_time < now() - interval '5 days'
"""

GET_NEAREST_LOCATION = """
    SELECT
        *,
        ST_Distance(coordinates, ST_SetSRID(ST_MakePoint($1, $2), 4326)) / 1000.0 AS distance_km
    FROM pakistan_locations
    WHERE is_active = TRUE
    ORDER BY coordinates <-> ST_SetSRID(ST_MakePoint($1, $2), 4326)
    LIMIT 1
"""