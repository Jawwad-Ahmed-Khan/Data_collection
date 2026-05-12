"""
ClimaSync Collection Service — Weather SQL Queries
"""

UPSERT_WEATHER_HOURLY = """
    INSERT INTO weather_hourly_window (
        location_id, location_key, location_name, district, province,
        latitude, longitude, coordinates, forecast_for_datetime,
        temp_c, temp_apparent_c, temp_dewpoint_c, precip_mm,
        precip_prob_pct, rain_mm, snowfall_cm, snow_depth_m,
        precip_3h_mm, precip_6h_mm, precip_12h_mm, precip_24h_mm, precip_72h_mm,
        wind_speed_kmh, wind_gusts_kmh, wind_direction_deg,
        humidity_pct, pressure_hpa,
        visibility_m, cloud_cover_pct, uv_index, cape_jkg,
        weather_code, weather_description,
        is_daytime, flag_extreme_heat, flag_heatwave,
        flag_heavy_rain, flag_very_heavy_rain, flag_storm,
        flag_severe_storm, flag_cold_wave, flag_dust_storm,
        flag_dense_fog, has_breach, breach_severity,
        breach_metric, breach_observed_value, breach_threshold_value,
        threshold_id, cycle_id
    ) VALUES (
        $1::uuid, $2, $3, $4, $5, $6::float8, $7::float8,
        ST_SetSRID(ST_MakePoint($7::float8, $6::float8), 4326),
        $8, $9, $10, $11, $12, $13, $14, $15, $16, 
        $17, $18, $19, $20, $21, $22, $23, $24,
        $25, $26, $27, $28, $29, $30, $31, $32, 
        $33, $34, $35, $36, $37, $38, $39, $40, $41, $42,
        $43, $44, $45, $46, $47, $48::uuid, $49::uuid
    )
    ON CONFLICT (location_id, forecast_for_datetime) DO UPDATE SET
        temp_c = EXCLUDED.temp_c,
        temp_apparent_c = EXCLUDED.temp_apparent_c,
        temp_dewpoint_c = EXCLUDED.temp_dewpoint_c,
        precip_mm = EXCLUDED.precip_mm,
        precip_prob_pct = EXCLUDED.precip_prob_pct,
        rain_mm = EXCLUDED.rain_mm,
        snowfall_cm = EXCLUDED.snowfall_cm,
        snow_depth_m = EXCLUDED.snow_depth_m,
        precip_3h_mm = EXCLUDED.precip_3h_mm,
        precip_6h_mm = EXCLUDED.precip_6h_mm,
        precip_12h_mm = EXCLUDED.precip_12h_mm,
        precip_24h_mm = EXCLUDED.precip_24h_mm,
        precip_72h_mm = EXCLUDED.precip_72h_mm,
        wind_speed_kmh = EXCLUDED.wind_speed_kmh,
        wind_gusts_kmh = EXCLUDED.wind_gusts_kmh,
        wind_direction_deg = EXCLUDED.wind_direction_deg,
        humidity_pct = EXCLUDED.humidity_pct,
        pressure_hpa = EXCLUDED.pressure_hpa,
        visibility_m = EXCLUDED.visibility_m,
        cloud_cover_pct = EXCLUDED.cloud_cover_pct,
        uv_index = EXCLUDED.uv_index,
        cape_jkg = EXCLUDED.cape_jkg,
        weather_code = EXCLUDED.weather_code,
        weather_description = EXCLUDED.weather_description,
        is_daytime = EXCLUDED.is_daytime,
        flag_extreme_heat = EXCLUDED.flag_extreme_heat,
        flag_heatwave = EXCLUDED.flag_heatwave,
        flag_heavy_rain = EXCLUDED.flag_heavy_rain,
        flag_very_heavy_rain = EXCLUDED.flag_very_heavy_rain,
        flag_storm = EXCLUDED.flag_storm,
        flag_severe_storm = EXCLUDED.flag_severe_storm,
        flag_cold_wave = EXCLUDED.flag_cold_wave,
        flag_dust_storm = EXCLUDED.flag_dust_storm,
        flag_dense_fog = EXCLUDED.flag_dense_fog,
        has_breach = EXCLUDED.has_breach,
        breach_severity = EXCLUDED.breach_severity,
        breach_metric = EXCLUDED.breach_metric,
        breach_observed_value = EXCLUDED.breach_observed_value,
        breach_threshold_value = EXCLUDED.breach_threshold_value,
        threshold_id = EXCLUDED.threshold_id,
        cycle_id = EXCLUDED.cycle_id,
        last_updated_at = now()
    RETURNING (xmax = 0) AS was_inserted
"""

UPSERT_WEATHER_DAILY = """
    INSERT INTO weather_daily_summaries (
        location_id, location_key, location_name, district, province,
        latitude, longitude, coordinates, summary_date,
        temp_max_c, temp_min_c, feels_like_max_c, feels_like_min_c,
        precip_total_mm, precip_prob_max_pct, wind_speed_max_kmh,
        wind_gusts_max_kmh, uv_index_max, sunrise_at, sunset_at,
        dominant_condition, flag_extreme_heat_day, flag_heatwave_day,
        flag_heavy_rain_day, flag_storm_day, flag_cold_wave_day,
        worst_breach_severity, cycle_id
    ) VALUES (
        $1::uuid, $2, $3, $4, $5, $6::float8, $7::float8,
        ST_SetSRID(ST_MakePoint($7::float8, $6::float8), 4326),
        $8, $9, $10, $11, $12, $13, $14, $15, 
        $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27::uuid
    )
    ON CONFLICT (location_id, summary_date) DO UPDATE SET
        temp_max_c = EXCLUDED.temp_max_c,
        temp_min_c = EXCLUDED.temp_min_c,
        feels_like_max_c = EXCLUDED.feels_like_max_c,
        feels_like_min_c = EXCLUDED.feels_like_min_c,
        precip_total_mm = EXCLUDED.precip_total_mm,
        precip_prob_max_pct = EXCLUDED.precip_prob_max_pct,
        wind_speed_max_kmh = EXCLUDED.wind_speed_max_kmh,
        wind_gusts_max_kmh = EXCLUDED.wind_gusts_max_kmh,
        uv_index_max = EXCLUDED.uv_index_max,
        sunrise_at = EXCLUDED.sunrise_at,
        sunset_at = EXCLUDED.sunset_at,
        dominant_condition = EXCLUDED.dominant_condition,
        flag_extreme_heat_day = EXCLUDED.flag_extreme_heat_day,
        flag_heatwave_day = EXCLUDED.flag_heatwave_day,
        flag_heavy_rain_day = EXCLUDED.flag_heavy_rain_day,
        flag_storm_day = EXCLUDED.flag_storm_day,
        flag_cold_wave_day = EXCLUDED.flag_cold_wave_day,
        worst_breach_severity = EXCLUDED.worst_breach_severity,
        cycle_id = EXCLUDED.cycle_id,
        last_updated_at = now()
    RETURNING (xmax = 0) AS was_inserted
"""

UPSERT_CURRENT_WEATHER_PER_LOCATION = """
    INSERT INTO current_weather_per_location (
        location_id, location_key, location_name, temp_c, temp_apparent_c,
        precip_mm, wind_speed_kmh, humidity_pct, pressure_hpa,
        weather_condition, weather_description, is_daytime, observation_time
    ) VALUES (
        $1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13
    )
    ON CONFLICT (location_id) DO UPDATE SET
        temp_c = EXCLUDED.temp_c,
        temp_apparent_c = EXCLUDED.temp_apparent_c,
        precip_mm = EXCLUDED.precip_mm,
        wind_speed_kmh = EXCLUDED.wind_speed_kmh,
        humidity_pct = EXCLUDED.humidity_pct,
        pressure_hpa = EXCLUDED.pressure_hpa,
        weather_condition = EXCLUDED.weather_condition,
        weather_description = EXCLUDED.weather_description,
        is_daytime = EXCLUDED.is_daytime,
        observation_time = EXCLUDED.observation_time,
        last_updated_at = now()
"""

UPSERT_WEATHER_5DAY_FORECAST = """
    INSERT INTO weather_5day_forecast_per_location (
        location_id, location_key, location_name, district, province,
        summary_date, day_offset, day_label, temp_max_c, temp_min_c,
        feels_like_max_c, precip_total_mm, precip_prob_max_pct,
        wind_speed_max_kmh, wind_gusts_max_kmh, uv_index_max,
        dominant_condition, sunrise_at, sunset_at,
        flag_extreme_heat_day, flag_heatwave_day, flag_heavy_rain_day,
        flag_storm_day, flag_cold_wave_day, worst_breach_severity
    ) VALUES (
        $1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
        $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25
    )
    ON CONFLICT (location_id, summary_date) DO UPDATE SET
        day_offset = EXCLUDED.day_offset,
        day_label = EXCLUDED.day_label,
        temp_max_c = EXCLUDED.temp_max_c,
        temp_min_c = EXCLUDED.temp_min_c,
        feels_like_max_c = EXCLUDED.feels_like_max_c,
        precip_total_mm = EXCLUDED.precip_total_mm,
        precip_prob_max_pct = EXCLUDED.precip_prob_max_pct,
        wind_speed_max_kmh = EXCLUDED.wind_speed_max_kmh,
        wind_gusts_max_kmh = EXCLUDED.wind_gusts_max_kmh,
        uv_index_max = EXCLUDED.uv_index_max,
        dominant_condition = EXCLUDED.dominant_condition,
        sunrise_at = EXCLUDED.sunrise_at,
        sunset_at = EXCLUDED.sunset_at,
        flag_extreme_heat_day = EXCLUDED.flag_extreme_heat_day,
        flag_heatwave_day = EXCLUDED.flag_heatwave_day,
        flag_heavy_rain_day = EXCLUDED.flag_heavy_rain_day,
        flag_storm_day = EXCLUDED.flag_storm_day,
        flag_cold_wave_day = EXCLUDED.flag_cold_wave_day,
        worst_breach_severity = EXCLUDED.worst_breach_severity,
        last_updated_at = now()
    RETURNING (xmax = 0) AS was_inserted
"""
