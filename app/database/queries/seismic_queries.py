"""
ClimaSync Collection Service — Seismic PostgreSQL Queries
"""

UPSERT_SEISMIC_EVENT = """
    INSERT INTO seismic_events (
        event_id,
        usgs_event_id,
        usgs_event_url,
        magnitude,
        magnitude_type,
        magnitude_class,
        depth_km,
        depth_class,
        latitude,
        longitude,
        coordinates,
        usgs_place,
        resolved_district,
        resolved_province,
        nearest_location_id,
        distance_to_nearest_km,
        felt_reports,
        cdi,
        mmi,
        tsunami_flag,
        usgs_alert_level,
        significance,
        station_count,
        azimuthal_gap_deg,
        rms_seconds,
        data_quality,
        contributing_networks,
        earthquake_time,
        usgs_last_updated_at,
        has_breach,
        breach_severity,
        threshold_id
    ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
        ST_SetSRID(ST_MakePoint($10, $9), 4326),
        $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28, $29, $30, $31
    )
    ON CONFLICT (usgs_event_id) DO UPDATE SET
        magnitude = EXCLUDED.magnitude,
        magnitude_type = EXCLUDED.magnitude_type,
        depth_km = EXCLUDED.depth_km,
        latitude = EXCLUDED.latitude,
        longitude = EXCLUDED.longitude,
        coordinates = ST_SetSRID(ST_MakePoint(EXCLUDED.longitude, EXCLUDED.latitude), 4326),
        usgs_place = EXCLUDED.usgs_place,
        felt_reports = EXCLUDED.felt_reports,
        cdi = EXCLUDED.cdi,
        mmi = EXCLUDED.mmi,
        tsunami_flag = EXCLUDED.tsunami_flag,
        usgs_alert_level = EXCLUDED.usgs_alert_level,
        significance = EXCLUDED.significance,
        station_count = EXCLUDED.station_count,
        azimuthal_gap_deg = EXCLUDED.azimuthal_gap_deg,
        rms_seconds = EXCLUDED.rms_seconds,
        contributing_networks = EXCLUDED.contributing_networks,
        data_quality = EXCLUDED.data_quality,
        earthquake_time = EXCLUDED.earthquake_time,
        usgs_last_updated_at = EXCLUDED.usgs_last_updated_at,
        has_breach = EXCLUDED.has_breach,
        breach_severity = EXCLUDED.breach_severity,
        threshold_id = EXCLUDED.threshold_id
    RETURNING event_id
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
