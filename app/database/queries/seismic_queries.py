"""
ClimaSync Collection Service — Seismic PostgreSQL Queries
"""

UPSERT_SEISMIC_EVENT = """
    INSERT INTO seismic_events (
        event_id,
        usgs_event_id,
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
        data_quality,
        earthquake_time,
        has_breach,
        breach_severity
    ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, 
        ST_SetSRID(ST_MakePoint($9, $8), 4326),
        $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24
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
        data_quality = EXCLUDED.data_quality,
        earthquake_time = EXCLUDED.earthquake_time,
        has_breach = EXCLUDED.has_breach,
        breach_severity = EXCLUDED.breach_severity
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
