-- CLIMASYNC.AI — DATA COLLECTION DATABASE
-- ============================================================================
-- Philosophy  : Rolling 5-day operational window (today + next 4 days)
-- Storage     : UPSERT-based. Data is refreshed, not accumulated.
-- Earthquake  : Current situation only (last 5 days, UPSERT on usgs_event_id)
-- Flood       : Current gauge state + 5-day forecast window
-- Weather     : 5-day hourly forecast window per location (120h × 270 loc)
-- Max Rows    : ~52,000 total — bounded, predictable, memory-resident fast
-- Environment : Supabase (PostgreSQL + PostGIS)
-- ============================================================================

-- ============================================================================
-- STEP 0: CLEAN SLATE
-- ============================================================================

DROP VIEW IF EXISTS collection_health_dashboard      CASCADE;
DROP VIEW IF EXISTS undispatched_breaches            CASCADE;
DROP VIEW IF EXISTS pakistan_risk_heatmap            CASCADE;
DROP VIEW IF EXISTS flood_situation_current          CASCADE;
DROP VIEW IF EXISTS active_breach_summary            CASCADE;
DROP VIEW IF EXISTS current_weather_per_location     CASCADE;
DROP VIEW IF EXISTS significant_recent_earthquakes   CASCADE;

DROP TABLE IF EXISTS threshold_breach_log            CASCADE;
DROP TABLE IF EXISTS flood_gauge_forecasts           CASCADE;
DROP TABLE IF EXISTS flood_gauge_current             CASCADE;
DROP TABLE IF EXISTS flood_gauge_registry            CASCADE;
DROP TABLE IF EXISTS seismic_events                  CASCADE;
DROP TABLE IF EXISTS weather_daily_summaries         CASCADE;
DROP TABLE IF EXISTS weather_hourly_window           CASCADE;
DROP TABLE IF EXISTS collection_cycles               CASCADE;
DROP TABLE IF EXISTS api_registry                    CASCADE;
DROP TABLE IF EXISTS disaster_thresholds             CASCADE;
DROP TABLE IF EXISTS pakistan_infrastructure         CASCADE;
DROP TABLE IF EXISTS pakistan_locations              CASCADE;

DROP FUNCTION IF EXISTS trigger_set_updated_at()              CASCADE;
DROP FUNCTION IF EXISTS compute_magnitude_category()          CASCADE;
DROP FUNCTION IF EXISTS compute_depth_category()              CASCADE;
DROP FUNCTION IF EXISTS decode_wmo_weather_code()             CASCADE;
DROP FUNCTION IF EXISTS compute_wind_cardinal()               CASCADE;
DROP FUNCTION IF EXISTS auto_set_weather_day_offset()         CASCADE;
DROP FUNCTION IF EXISTS update_api_health_on_cycle()          CASCADE;
DROP FUNCTION IF EXISTS prevent_weather_update_past_window()  CASCADE;
DROP FUNCTION IF EXISTS cleanup_expired_window_data()         CASCADE;

DROP TYPE IF EXISTS api_source_name          CASCADE;
DROP TYPE IF EXISTS api_health_state         CASCADE;
DROP TYPE IF EXISTS cycle_status             CASCADE;
DROP TYPE IF EXISTS poll_outcome             CASCADE;
DROP TYPE IF EXISTS pk_province              CASCADE;
DROP TYPE IF EXISTS location_tier            CASCADE;
DROP TYPE IF EXISTS poll_priority            CASCADE;
DROP TYPE IF EXISTS asset_type              CASCADE;
DROP TYPE IF EXISTS vulnerability_level      CASCADE;
DROP TYPE IF EXISTS risk_zone               CASCADE;
DROP TYPE IF EXISTS disaster_kind            CASCADE;
DROP TYPE IF EXISTS weather_condition        CASCADE;
DROP TYPE IF EXISTS breach_level             CASCADE;
DROP TYPE IF EXISTS flood_status             CASCADE;
DROP TYPE IF EXISTS river_trend              CASCADE;
DROP TYPE IF EXISTS magnitude_class          CASCADE;
DROP TYPE IF EXISTS depth_class              CASCADE;
DROP TYPE IF EXISTS seismic_data_quality     CASCADE;
DROP TYPE IF EXISTS breach_dispatch_status   CASCADE;


-- ============================================================================
-- STEP 1: EXTENSIONS
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS citext;


-- ============================================================================
-- STEP 2: TIMEZONE
-- ============================================================================

SET TIME ZONE 'UTC';


-- ============================================================================
-- STEP 3: SHARED UTILITY FUNCTION
-- ============================================================================

CREATE OR REPLACE FUNCTION trigger_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ============================================================================
-- STEP 4: ENUMS (17 total — only what is operationally necessary)
-- ============================================================================

-- Which external API produced this data
CREATE TYPE api_source_name AS ENUM (
    'usgs',
    'open_meteo',
    'google_flood_hub'
);

-- Live health state of each external API
CREATE TYPE api_health_state AS ENUM (
    'healthy',
    'degraded',
    'rate_limited',
    'down',
    'unknown'
);

-- Status of a data collection cycle execution
CREATE TYPE cycle_status AS ENUM (
    'running',
    'completed',
    'partial',
    'failed',
    'skipped'
);

-- Result of a single API call to a single location
CREATE TYPE poll_outcome AS ENUM (
    'success',
    'failed',
    'rate_limited',
    'timeout',
    'invalid_response',
    'skipped'
);

-- Pakistan administrative provinces and territories
CREATE TYPE pk_province AS ENUM (
    'punjab',
    'sindh',
    'khyber_pakhtunkhwa',
    'balochistan',
    'gilgit_baltistan',
    'azad_kashmir',
    'islamabad_capital_territory'
);

-- Classification of monitoring location by strategic importance
CREATE TYPE location_tier AS ENUM (
    'tier_1_provincial_capital',
    'tier_2_district_headquarters',
    'tier_3_disaster_zone',
    'tier_3_river_basin',
    'tier_3_coastal',
    'tier_3_mountain',
    'tier_3_border'
);

-- Priority level for polling scheduler
CREATE TYPE poll_priority AS ENUM (
    'critical',
    'high',
    'medium',
    'low'
);

-- Infrastructure asset classification
CREATE TYPE asset_type AS ENUM (
    'hospital',
    'basic_health_unit',
    'school',
    'bridge',
    'dam',
    'barrage',
    'power_station',
    'water_treatment',
    'airport',
    'flood_shelter',
    'evacuation_center'
);

-- General vulnerability rating
CREATE TYPE vulnerability_level AS ENUM (
    'very_low',
    'low',
    'moderate',
    'high',
    'very_high',
    'critical'
);

-- Seismic and flood risk zone classification
CREATE TYPE risk_zone AS ENUM (
    'zone_1_low',
    'zone_2_moderate',
    'zone_3_high',
    'zone_4_very_high',
    'zone_5_critical'
);

-- Type of disaster event being tracked
CREATE TYPE disaster_kind AS ENUM (
    'earthquake',
    'flood',
    'flash_flood',
    'heatwave',
    'cyclone',
    'heavy_rain',
    'drought',
    'landslide',
    'dust_storm',
    'cold_wave'
);

-- Decoded WMO weather code category
CREATE TYPE weather_condition AS ENUM (
    'clear',
    'partly_cloudy',
    'overcast',
    'fog',
    'drizzle',
    'rain',
    'heavy_rain',
    'freezing_rain',
    'snow',
    'heavy_snow',
    'rain_showers',
    'snow_showers',
    'thunderstorm',
    'thunderstorm_with_hail',
    'dust_storm',
    'haze'
);

-- Severity level when a disaster threshold is crossed
CREATE TYPE breach_level AS ENUM (
    'watch',        -- approaching threshold, not yet crossed
    'warning',      -- threshold crossed
    'emergency',    -- critical threshold crossed
    'extreme'       -- extreme/catastrophic threshold crossed
);

-- Google Flood Hub official flood classification
CREATE TYPE flood_status AS ENUM (
    'no_flooding',
    'watch',
    'warning',
    'emergency'
);

-- Direction of river level change
CREATE TYPE river_trend AS ENUM (
    'rapidly_rising',
    'rising',
    'stable',
    'falling',
    'rapidly_falling'
);

-- Earthquake magnitude classification
CREATE TYPE magnitude_class AS ENUM (
    'micro',        -- < 2.0
    'minor',        -- 2.0–3.9
    'light',        -- 4.0–4.9
    'moderate',     -- 5.0–5.9
    'strong',       -- 6.0–6.9
    'major',        -- 7.0–7.9
    'great'         -- 8.0+
);

-- Earthquake depth classification
CREATE TYPE depth_class AS ENUM (
    'shallow',      -- 0–70 km   (most destructive)
    'intermediate', -- 70–300 km
    'deep'          -- 300+ km
);

-- USGS data processing status
CREATE TYPE seismic_data_quality AS ENUM (
    'automatic',    -- seismic algorithm only, not human reviewed
    'reviewed',     -- human geologist verified
    'deleted'       -- USGS removed this event (false detection)
);

-- Dispatch state of a threshold breach to the main ClimaSync system
CREATE TYPE breach_dispatch_status AS ENUM (
    'pending',          -- waiting to be sent
    'dispatched',       -- sent to main system successfully
    'suppressed',       -- duplicate — suppressed, not sent
    'dispatch_failed'   -- attempt to send failed, will retry
);


-- ============================================================================
-- REFERENCE TABLE 1: api_registry
-- One row per external API. Persists health and rate-limit state.
-- ============================================================================

CREATE TABLE api_registry (
    api_id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    api_name                    api_source_name NOT NULL UNIQUE,
    display_name                VARCHAR(100)    NOT NULL,
    base_url                    TEXT            NOT NULL,
    documentation_url           TEXT,

    -- Rate limiting configuration
    max_requests_per_minute     INT  NOT NULL DEFAULT 60,
    max_requests_per_day        INT  NOT NULL DEFAULT 10000,
    min_delay_between_calls_ms  INT  NOT NULL DEFAULT 300,

    -- Exponential backoff configuration
    initial_backoff_s           INT          NOT NULL DEFAULT 5,
    max_backoff_s               INT          NOT NULL DEFAULT 600,
    backoff_multiplier          DECIMAL(4,2) NOT NULL DEFAULT 2.0,

    -- Live health state
    -- (updated by collection service after every cycle)
    current_health              api_health_state NOT NULL DEFAULT 'unknown',
    last_success_at             TIMESTAMPTZ,
    last_failure_at             TIMESTAMPTZ,
    consecutive_failures        SMALLINT NOT NULL DEFAULT 0,
    avg_latency_ms              INT,
    -- rolling average updated each cycle

    -- Rate limit window state
    -- persisted so server restart does not lose rate-limit context
    rate_window_start_at        TIMESTAMPTZ,
    calls_in_window             INT NOT NULL DEFAULT 0,
    backoff_until               TIMESTAMPTZ,
    -- do not call this API until this timestamp

    is_active                   BOOLEAN NOT NULL DEFAULT TRUE,
    notes                       TEXT,

    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT api_backoff_multiplier_valid
        CHECK (backoff_multiplier >= 1.0),
    CONSTRAINT api_delay_positive
        CHECK (min_delay_between_calls_ms >= 0)
);

CREATE TRIGGER trg_api_registry_updated_at
    BEFORE UPDATE ON api_registry
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();


-- ============================================================================
-- REFERENCE TABLE 2: pakistan_locations
-- Master list of 270 monitoring coordinate points across Pakistan.
-- Drives the Open-Meteo polling scheduler.
-- Also used for coordinate-to-district resolution for USGS/Flood data.
-- ============================================================================

CREATE TABLE pakistan_locations (
    location_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Deterministic key used for joins and cache keys
    location_key            VARCHAR(120) NOT NULL UNIQUE,
    -- Format: "lahore_31.5497_74.3436"

    location_name           VARCHAR(255) NOT NULL,
    local_name              VARCHAR(255),
    -- Urdu or regional name for display

    location_tier           location_tier NOT NULL,

    -- Administrative hierarchy
    district                VARCHAR(100) NOT NULL,
    division                VARCHAR(100),
    province                pk_province  NOT NULL,

    -- Geographic
    coordinates             GEOGRAPHY(POINT, 4326) NOT NULL,
    latitude                DECIMAL(10,7) NOT NULL,
    longitude               DECIMAL(10,7) NOT NULL,
    elevation_m             INT,

    -- Population context
    -- used by Risk Analysis Agent to estimate impact
    population              BIGINT,
    population_density      DECIMAL(10,2),
    -- persons per square km

    -- Static risk profile
    -- pre-assessed by domain experts, rarely changes
    flood_risk_zone         risk_zone,
    seismic_zone            VARCHAR(5),
    -- Pakistan seismic zone: I / II / III / IV
    heat_risk_zone          risk_zone,
    drought_risk_zone       risk_zone,
    infrastructure_quality  vulnerability_level,
    drainage_quality        vulnerability_level,
    building_stock          VARCHAR(50),
    -- 'kutcha' / 'semi_pucca' / 'pucca' / 'mixed'

    -- Polling configuration
    poll_priority           poll_priority NOT NULL DEFAULT 'medium',
    poll_interval_minutes   INT           NOT NULL DEFAULT 180,
    -- how frequently to call Open-Meteo for this location

    -- Polling state (updated by trigger after each poll)
    last_polled_at          TIMESTAMPTZ,
    last_poll_outcome       poll_outcome,
    next_poll_due_at        TIMESTAMPTZ,
    consecutive_failures    SMALLINT NOT NULL DEFAULT 0,

    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    data_source             VARCHAR(100),
    -- PBS / OSM / NADRA / manual

    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT loc_latitude_pk_bounds
        CHECK (latitude  BETWEEN 23.0 AND 38.0),
    CONSTRAINT loc_longitude_pk_bounds
        CHECK (longitude BETWEEN 60.0 AND 78.0),
    CONSTRAINT loc_poll_interval_minimum
        CHECK (poll_interval_minutes >= 30),
    CONSTRAINT loc_population_positive
        CHECK (population IS NULL OR population > 0)
);

CREATE INDEX idx_loc_coordinates
    ON pakistan_locations USING GIST(coordinates);

CREATE INDEX idx_loc_province_district
    ON pakistan_locations(province, district)
    WHERE is_active = TRUE;

CREATE INDEX idx_loc_poll_due
    ON pakistan_locations(next_poll_due_at, poll_priority)
    WHERE is_active = TRUE;

CREATE TRIGGER trg_locations_updated_at
    BEFORE UPDATE ON pakistan_locations
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();


-- ============================================================================
-- REFERENCE TABLE 3: pakistan_infrastructure
-- Critical assets. Used by Risk Analysis Agent.
-- Static reference data — very rarely changes.
-- ============================================================================

CREATE TABLE pakistan_infrastructure (
    asset_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    location_id         UUID REFERENCES pakistan_locations(location_id)
                            ON DELETE SET NULL,

    asset_name          VARCHAR(255) NOT NULL,
    asset_type          asset_type   NOT NULL,

    coordinates         GEOGRAPHY(POINT, 4326) NOT NULL,
    latitude            DECIMAL(10,7) NOT NULL,
    longitude           DECIMAL(10,7) NOT NULL,
    district            VARCHAR(100),
    province            pk_province,

    capacity            INT,
    capacity_unit       VARCHAR(30),
    -- 'beds' / 'students' / 'MW' / 'persons'

    vulnerability_score DECIMAL(4,2),
    -- 0.00 to 10.00
    vulnerability_level vulnerability_level,
    is_seismic_resistant BOOLEAN DEFAULT FALSE,
    is_flood_resistant   BOOLEAN DEFAULT FALSE,

    is_critical         BOOLEAN NOT NULL DEFAULT FALSE,
    -- TRUE = serves >10,000 people or unique in district
    serves_population   INT,

    data_source         VARCHAR(100),
    external_id         VARCHAR(255) UNIQUE,
    last_verified_at    TIMESTAMPTZ,

    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    notes               TEXT,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT infra_vulnerability_range
        CHECK (vulnerability_score IS NULL
               OR vulnerability_score BETWEEN 0 AND 10),
    CONSTRAINT infra_capacity_positive
        CHECK (capacity IS NULL OR capacity > 0)
);

CREATE INDEX idx_infra_coordinates
    ON pakistan_infrastructure USING GIST(coordinates);

CREATE INDEX idx_infra_type_province
    ON pakistan_infrastructure(asset_type, province)
    WHERE is_active = TRUE;

CREATE INDEX idx_infra_critical
    ON pakistan_infrastructure(district)
    WHERE is_critical = TRUE AND is_active = TRUE;

CREATE TRIGGER trg_infra_updated_at
    BEFORE UPDATE ON pakistan_infrastructure
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();


-- ============================================================================
-- REFERENCE TABLE 4: disaster_thresholds
-- Pakistan-specific, province-specific, season-specific threshold values.
-- Collection service reads this to decide when to fire a breach alert.
-- ============================================================================

CREATE TABLE disaster_thresholds (
    threshold_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    disaster_kind       disaster_kind NOT NULL,
    metric_name         VARCHAR(100)  NOT NULL,
    -- Standardized metric identifiers:
    -- temp_max_c            feels_like_max_c       temp_min_c
    -- precip_1h_mm          precip_6h_mm           precip_24h_mm
    -- precip_72h_mm         wind_speed_kmh         wind_gusts_kmh
    -- humidity_pct          uv_index               cape_jkg
    -- magnitude             gauge_level_m          gauge_pct_of_danger
    -- gauge_rise_rate_m_per_hour

    -- Geographic scope (NULL = broader scope applies)
    province            pk_province,  -- NULL = national default
    district            VARCHAR(100), -- NULL = province-wide

    -- Seasonal scope (NULL = year-round)
    applies_season      VARCHAR(20),
    -- 'monsoon'     = July–September
    -- 'pre_monsoon' = April–June
    -- 'summer'      = March–June
    -- 'winter'      = December–February
    -- NULL          = applies all year

    -- Threshold values at each severity level
    watch_threshold     DECIMAL(12,4),
    warning_threshold   DECIMAL(12,4),
    emergency_threshold DECIMAL(12,4),
    extreme_threshold   DECIMAL(12,4),

    -- Whether breach is triggered when value goes above or below threshold
    breach_direction    VARCHAR(5) NOT NULL DEFAULT 'above',
    -- 'above' : value > threshold → breach (heat, rain, wind, flood)
    -- 'below' : value < threshold → breach (cold wave, drought)

    unit                VARCHAR(30) NOT NULL,
    description         TEXT,
    data_source         VARCHAR(100),
    -- NDMA / PMD / WMO / expert_judgment

    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    last_reviewed_at    TIMESTAMPTZ,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT threshold_direction_valid
        CHECK (breach_direction IN ('above', 'below')),
    CONSTRAINT threshold_metric_not_empty
        CHECK (char_length(trim(metric_name)) > 0)
);

-- Partial unique indexes to handle NULL semantics correctly
-- A national default exists when province and district are both NULL
CREATE UNIQUE INDEX idx_threshold_national
    ON disaster_thresholds(disaster_kind, metric_name)
    WHERE province IS NULL
      AND district IS NULL
      AND applies_season IS NULL
      AND is_active = TRUE;

CREATE UNIQUE INDEX idx_threshold_province
    ON disaster_thresholds(disaster_kind, metric_name, province)
    WHERE district IS NULL
      AND applies_season IS NULL
      AND province IS NOT NULL
      AND is_active = TRUE;

CREATE INDEX idx_threshold_lookup
    ON disaster_thresholds(disaster_kind, metric_name)
    WHERE is_active = TRUE;

CREATE TRIGGER trg_thresholds_updated_at
    BEFORE UPDATE ON disaster_thresholds
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();


-- ============================================================================
-- REFERENCE TABLE 5: flood_gauge_registry
-- Static properties of each Google Flood Hub river gauge.
-- One row per physical gauge — never changes unless WAPDA adds a new gauge.
-- ============================================================================

CREATE TABLE flood_gauge_registry (
    gauge_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    google_gauge_id     VARCHAR(100) NOT NULL UNIQUE,
    gauge_name          VARCHAR(255) NOT NULL,
    official_gauge_code VARCHAR(50),
    -- WAPDA / PMD official code

    river_name          VARCHAR(255) NOT NULL,
    river_system        VARCHAR(100),
    -- 'Indus' / 'Jhelum-Chenab' / 'Ravi-Sutlej' / 'Kabul' / 'Coastal'
    basin_name          VARCHAR(255),
    upstream_area_sqkm  DECIMAL(12,2),

    coordinates         GEOGRAPHY(POINT, 4326) NOT NULL,
    latitude            DECIMAL(10,7) NOT NULL,
    longitude           DECIMAL(10,7) NOT NULL,
    district            VARCHAR(100),
    province            pk_province,
    nearest_location_id UUID REFERENCES pakistan_locations(location_id)
                            ON DELETE SET NULL,

    -- Static threshold levels from NDMA / WAPDA
    normal_level_m      DECIMAL(8,3),
    bankfull_level_m    DECIMAL(8,3),
    warning_level_m     DECIMAL(8,3),
    danger_level_m      DECIMAL(8,3),
    extreme_level_m     DECIMAL(8,3),
    historical_max_m    DECIMAL(8,3),

    poll_priority       poll_priority NOT NULL DEFAULT 'high',
    -- gauges are always high priority during monsoon
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    data_source         VARCHAR(100),
    notes               TEXT,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_gauge_coordinates
    ON flood_gauge_registry USING GIST(coordinates);

CREATE INDEX idx_gauge_province_river
    ON flood_gauge_registry(province, river_name)
    WHERE is_active = TRUE;

CREATE TRIGGER trg_gauge_registry_updated_at
    BEFORE UPDATE ON flood_gauge_registry
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();


-- ============================================================================
-- OPERATIONAL TABLE 1: collection_cycles
-- One row per API polling cycle execution.
-- Gives complete visibility into collection health.
-- ============================================================================

CREATE TABLE collection_cycles (
    cycle_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    api_id              UUID            NOT NULL
                            REFERENCES api_registry(api_id)
                            ON DELETE RESTRICT,
    api_name            api_source_name NOT NULL,
    -- denormalized to avoid join in health queries

    cycle_type          VARCHAR(30) NOT NULL DEFAULT 'scheduled',
    -- 'scheduled' / 'priority_refresh' / 'manual' / 'startup' / 'retry'

    status              cycle_status NOT NULL DEFAULT 'running',

    -- Coverage counts
    locations_targeted  INT NOT NULL DEFAULT 0,
    locations_success   INT NOT NULL DEFAULT 0,
    locations_failed    INT NOT NULL DEFAULT 0,
    locations_skipped   INT NOT NULL DEFAULT 0,

    -- Data write counts
    rows_upserted       INT NOT NULL DEFAULT 0,
    -- weather: updated existing forecast rows
    rows_inserted       INT NOT NULL DEFAULT 0,
    -- new rows created (new forecast hours, new earthquake events)
    rows_deleted        INT NOT NULL DEFAULT 0,
    -- rows cleaned up by window expiry during this cycle
    breaches_triggered  INT NOT NULL DEFAULT 0,

    -- API call stats
    total_api_calls     INT NOT NULL DEFAULT 0,
    rate_limit_hits     INT NOT NULL DEFAULT 0,
    total_bytes         BIGINT DEFAULT 0,

    -- Performance
    started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at        TIMESTAMPTZ,
    duration_ms         INT,
    avg_latency_ms      INT,

    -- Error detail
    error_summary       JSONB,
    -- {"lahore_31.5497_74.3436": "timeout after 30s"}
    failure_reason      TEXT,

    -- Identity
    triggered_by        VARCHAR(50) DEFAULT 'scheduler',
    server_id           VARCHAR(100),

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT cycle_completed_after_started
        CHECK (completed_at IS NULL OR completed_at >= started_at),
    CONSTRAINT cycle_counts_non_negative
        CHECK (locations_targeted  >= 0
           AND locations_success   >= 0
           AND locations_failed    >= 0
           AND rows_upserted       >= 0
           AND rows_inserted       >= 0)
);

CREATE INDEX idx_cycles_api_started
    ON collection_cycles(api_id, started_at DESC);

CREATE INDEX idx_cycles_running
    ON collection_cycles(status)
    WHERE status = 'running';

CREATE INDEX idx_cycles_recent
    ON collection_cycles(started_at DESC);


-- ============================================================================
-- TIME-SERIES TABLE 1: weather_hourly_window
--
-- THE CORE ROLLING WINDOW TABLE.
--
-- Stores weather data for every location for every hour
-- from today 00:00 UTC through today+4 days 23:00 UTC.
-- That is exactly 120 hours × 270 locations = 32,400 rows maximum.
-- This count NEVER grows — rows are upserted, not accumulated.
--
-- PRIMARY KEY: (location_id, forecast_for_datetime)
-- This composite unique constraint enforces UPSERT correctness.
-- When a fresher forecast arrives for location X at hour H,
-- it updates the existing row, not inserts a new one.
--
-- DELETION: Daily cleanup job deletes WHERE
--           DATE(forecast_for_datetime) < CURRENT_DATE
-- ============================================================================

CREATE TABLE weather_hourly_window (
    -- Composite natural primary key
    -- represents "what weather at this place at this hour"
    location_id             UUID        NOT NULL
                                REFERENCES pakistan_locations(location_id)
                                ON DELETE CASCADE,
    forecast_for_datetime   TIMESTAMPTZ NOT NULL,
    -- The specific hour this row represents
    -- e.g. 2025-07-15 09:00:00+00

    -- Computed from forecast_for_datetime at upsert time
    forecast_date           DATE        NOT NULL,
    -- DATE(forecast_for_datetime AT TIME ZONE 'Asia/Karachi')
    day_offset              SMALLINT    NOT NULL,
    -- 0 = today, 1 = tomorrow, 2 = day after, up to 4

    -- Denormalized location context
    -- copied from pakistan_locations at upsert time
    location_key            VARCHAR(120) NOT NULL,
    location_name           VARCHAR(255) NOT NULL,
    district                VARCHAR(100) NOT NULL,
    province                pk_province  NOT NULL,
    latitude                DECIMAL(10,7) NOT NULL,
    longitude               DECIMAL(10,7) NOT NULL,
    coordinates             GEOGRAPHY(POINT, 4326) NOT NULL,

    -- Source tracking
    cycle_id                UUID REFERENCES collection_cycles(cycle_id)
                                ON DELETE SET NULL,
    last_updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- when this row was last written by the collection service
    data_freshness_minutes  INT,
    -- minutes between scheduled poll and actual poll completion

    -- ── TEMPERATURE ───────────────────────────────────────────────────────────
    temp_c                  DECIMAL(5,2),
    temp_apparent_c         DECIMAL(5,2),   -- feels like
    temp_dewpoint_c         DECIMAL(5,2),

    -- ── PRECIPITATION ─────────────────────────────────────────────────────────
    precip_mm               DECIMAL(7,3),   -- precipitation this hour
    precip_prob_pct         SMALLINT,       -- probability 0-100
    rain_mm                 DECIMAL(7,3),
    snowfall_cm             DECIMAL(6,3),
    snow_depth_m            DECIMAL(6,3),

    -- Rolling accumulations
    -- computed from this row and preceding rows in the same location
    -- recalculated on every upsert for the affected location
    precip_3h_mm            DECIMAL(8,3),
    precip_6h_mm            DECIMAL(8,3),
    precip_12h_mm           DECIMAL(9,3),
    precip_24h_mm           DECIMAL(9,3),
    precip_72h_mm           DECIMAL(10,3),

    -- ── WIND ──────────────────────────────────────────────────────────────────
    wind_speed_kmh          DECIMAL(6,2),
    wind_gusts_kmh          DECIMAL(6,2),
    wind_direction_deg      SMALLINT,
    wind_direction_cardinal VARCHAR(3),
    -- auto-computed by trigger: N / NE / E / SE / S / SW / W / NW

    -- ── ATMOSPHERIC ───────────────────────────────────────────────────────────
    humidity_pct            SMALLINT,
    pressure_hpa            DECIMAL(8,2),
    visibility_m            INT,
    cloud_cover_pct         SMALLINT,
    uv_index                DECIMAL(4,2),

    -- ── STORM SEVERITY INDICATOR ──────────────────────────────────────────────
    cape_jkg                DECIMAL(8,2),
    -- Convective Available Potential Energy
    -- > 1000 = thunderstorm risk
    -- > 2500 = severe thunderstorm risk
    -- > 3500 = violent storm risk

    -- ── WEATHER CLASSIFICATION ────────────────────────────────────────────────
    weather_code            SMALLINT,
    -- Raw WMO weather code from Open-Meteo
    weather_condition       weather_condition,
    -- auto-decoded by trigger from weather_code
    weather_description     VARCHAR(150),
    -- human-readable label
    is_daytime              BOOLEAN,

    -- ── DISASTER FLAGS (set by collection service at write time) ───────────────
    flag_extreme_heat       BOOLEAN NOT NULL DEFAULT FALSE,
    flag_heatwave           BOOLEAN NOT NULL DEFAULT FALSE,
    -- heatwave = temp above threshold for 3+ consecutive days
    flag_heavy_rain         BOOLEAN NOT NULL DEFAULT FALSE,
    flag_very_heavy_rain    BOOLEAN NOT NULL DEFAULT FALSE,
    flag_storm              BOOLEAN NOT NULL DEFAULT FALSE,
    flag_severe_storm       BOOLEAN NOT NULL DEFAULT FALSE,
    -- cape_jkg > 2500 + thunderstorm weather code
    flag_cold_wave          BOOLEAN NOT NULL DEFAULT FALSE,
    flag_dust_storm         BOOLEAN NOT NULL DEFAULT FALSE,
    flag_dense_fog          BOOLEAN NOT NULL DEFAULT FALSE,

    -- ── THRESHOLD BREACH ──────────────────────────────────────────────────────
    has_breach              BOOLEAN NOT NULL DEFAULT FALSE,
    breach_severity         breach_level,    -- NULL if no breach
    breach_metric           VARCHAR(100),    -- which metric breached
    breach_observed_value   DECIMAL(12,4),   -- the actual value
    breach_threshold_value  DECIMAL(12,4),   -- the threshold that was crossed
    threshold_id            UUID REFERENCES disaster_thresholds(threshold_id)
                                ON DELETE SET NULL,

    PRIMARY KEY (location_id, forecast_for_datetime),

    CONSTRAINT weather_window_temp_range
        CHECK (temp_c IS NULL OR temp_c BETWEEN -30 AND 60),
    CONSTRAINT weather_window_humidity_range
        CHECK (humidity_pct IS NULL
               OR humidity_pct BETWEEN 0 AND 100),
    CONSTRAINT weather_window_precip_non_negative
        CHECK (precip_mm IS NULL OR precip_mm >= 0),
    CONSTRAINT weather_window_wind_non_negative
        CHECK (wind_speed_kmh IS NULL OR wind_speed_kmh >= 0),
    CONSTRAINT weather_window_uv_range
        CHECK (uv_index IS NULL OR uv_index BETWEEN 0 AND 20),
    CONSTRAINT weather_window_day_offset_range
        CHECK (day_offset BETWEEN 0 AND 5),
    CONSTRAINT weather_window_cape_non_negative
        CHECK (cape_jkg IS NULL OR cape_jkg >= 0)
);

CREATE INDEX idx_weather_window_location_datetime
    ON weather_hourly_window(location_id, forecast_for_datetime);

CREATE INDEX idx_weather_window_district_datetime
    ON weather_hourly_window(district, forecast_for_datetime);

CREATE INDEX idx_weather_window_breach
    ON weather_hourly_window(forecast_for_datetime, breach_severity)
    WHERE has_breach = TRUE;

CREATE INDEX idx_weather_window_extreme_heat
    ON weather_hourly_window(province, forecast_for_datetime)
    WHERE flag_extreme_heat = TRUE;

CREATE INDEX idx_weather_window_heavy_rain
    ON weather_hourly_window(province, forecast_for_datetime)
    WHERE flag_heavy_rain = TRUE;

CREATE INDEX idx_weather_window_day_offset
    ON weather_hourly_window(location_id, day_offset);


-- ============================================================================
-- TIME-SERIES TABLE 2: weather_daily_summaries
--
-- One row per location per day for the 5-day window.
-- Maximum: 270 locations × 5 days = 1,350 rows. Never grows beyond this.
-- UPSERT on (location_id, summary_date).
-- Direct from Open-Meteo daily response — not aggregated from hourly.
--
-- DELETION: Daily cleanup deletes WHERE summary_date < CURRENT_DATE
-- ============================================================================

CREATE TABLE weather_daily_summaries (
    location_id             UUID NOT NULL
                                REFERENCES pakistan_locations(location_id)
                                ON DELETE CASCADE,
    summary_date            DATE NOT NULL,

    day_offset              SMALLINT NOT NULL,
    -- 0 = today, 1 = tomorrow ... 4

    -- Denormalized
    location_key            VARCHAR(120) NOT NULL,
    location_name           VARCHAR(255) NOT NULL,
    district                VARCHAR(100) NOT NULL,
    province                pk_province  NOT NULL,

    latitude                DECIMAL(10,7) NOT NULL,
    longitude               DECIMAL(10,7) NOT NULL,
    coordinates             GEOGRAPHY(POINT, 4326) NOT NULL,

    -- Source
    cycle_id                UUID REFERENCES collection_cycles(cycle_id)
                                ON DELETE SET NULL,
    last_updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Temperature
    temp_max_c              DECIMAL(5,2),
    temp_min_c              DECIMAL(5,2),
    feels_like_max_c        DECIMAL(5,2),
    feels_like_min_c        DECIMAL(5,2),

    -- Precipitation
    precip_total_mm         DECIMAL(9,3),
    rain_total_mm           DECIMAL(9,3),
    snowfall_total_cm       DECIMAL(8,3),
    precip_hours            SMALLINT,
    precip_prob_max_pct     SMALLINT,

    -- Wind
    wind_speed_max_kmh      DECIMAL(6,2),
    wind_gusts_max_kmh      DECIMAL(6,2),
    wind_dominant_cardinal  VARCHAR(3),

    -- Day overview
    dominant_condition      weather_condition,
    weather_code_dominant   SMALLINT,
    uv_index_max            DECIMAL(4,2),
    sunrise_at              TIMESTAMPTZ,
    sunset_at               TIMESTAMPTZ,
    daylight_hours          DECIMAL(4,2),

    -- Day-level disaster flags
    flag_extreme_heat_day   BOOLEAN DEFAULT FALSE,
    flag_heatwave_day       BOOLEAN DEFAULT FALSE,
    flag_heavy_rain_day     BOOLEAN DEFAULT FALSE,
    flag_storm_day          BOOLEAN DEFAULT FALSE,
    flag_cold_wave_day      BOOLEAN DEFAULT FALSE,
    worst_breach_severity   breach_level,
    -- worst breach recorded in any hour of this day

    PRIMARY KEY (location_id, summary_date),

    CONSTRAINT daily_summary_day_offset_range
        CHECK (day_offset BETWEEN 0 AND 5),
    CONSTRAINT daily_summary_date_not_past
        CHECK (summary_date >= CURRENT_DATE - INTERVAL '1 day')
    -- small tolerance for timezone differences
);

CREATE INDEX idx_daily_summary_district_date
    ON weather_daily_summaries(district, summary_date);

CREATE INDEX idx_daily_summary_breach
    ON weather_daily_summaries(summary_date)
    WHERE worst_breach_severity IS NOT NULL;

CREATE INDEX idx_daily_summary_province_date
    ON weather_daily_summaries(province, summary_date);


-- ============================================================================
-- TIME-SERIES TABLE 3: seismic_events
--
-- Rolling 5-day window of earthquake events within Pakistan.
-- UPSERT on usgs_event_id — USGS refines magnitude for hours after event.
-- The row always reflects the CURRENT BEST USGS estimate.
-- Maximum ~75 rows (15 events/day × 5 days). Usually far fewer.
--
-- DELETION: Daily cleanup deletes WHERE
--           DATE(earthquake_time) < CURRENT_DATE - INTERVAL '4 days'
-- ============================================================================

CREATE TABLE seismic_events (
    event_id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- USGS unique identifier — THE key for upsert logic
    usgs_event_id           VARCHAR(50) NOT NULL UNIQUE,
    usgs_event_url          TEXT,

    -- Source tracking
    cycle_id                UUID REFERENCES collection_cycles(cycle_id)
                                ON DELETE SET NULL,

    -- Classification (auto-computed by triggers)
    magnitude               DECIMAL(4,2)      NOT NULL,
    magnitude_type          VARCHAR(10),
    -- ml / mb / mw / ms / md
    magnitude_class         magnitude_class   NOT NULL,
    -- auto-set by trigger based on magnitude value

    -- Location
    coordinates             GEOGRAPHY(POINT, 4326) NOT NULL,
    latitude                DECIMAL(10,7) NOT NULL,
    longitude               DECIMAL(10,7) NOT NULL,
    depth_km                DECIMAL(8,3),
    depth_class             depth_class,
    -- auto-set by trigger based on depth_km value

    -- USGS place string and resolved Pakistan admin context
    usgs_place              VARCHAR(500),
    -- e.g. "23km NNE of Muzaffarabad, Pakistan"
    resolved_district       VARCHAR(100),
    resolved_province       pk_province,
    nearest_location_id     UUID REFERENCES pakistan_locations(location_id)
                                ON DELETE SET NULL,
    distance_to_nearest_km  DECIMAL(8,2),

    -- Impact data from USGS
    felt_reports            INT     DEFAULT 0,
    cdi                     DECIMAL(4,2),
    -- Community Decimal Intensity 0–10
    mmi                     DECIMAL(4,2),
    -- Modified Mercalli Intensity 0–10
    tsunami_flag            BOOLEAN NOT NULL DEFAULT FALSE,
    usgs_alert_level        VARCHAR(10),
    -- green / yellow / orange / red (PAGER system)
    significance            INT,
    -- USGS significance 0–1000

    -- Data quality indicators
    station_count           SMALLINT,
    azimuthal_gap_deg       DECIMAL(6,2),
    -- > 180 means location estimate is less reliable
    rms_seconds             DECIMAL(6,4),
    data_quality            seismic_data_quality NOT NULL DEFAULT 'automatic',
    contributing_networks   TEXT[],
    -- e.g. ['us', 'ak', 'ci']

    -- Threshold breach
    has_breach              BOOLEAN NOT NULL DEFAULT FALSE,
    breach_severity         breach_level,
    threshold_id            UUID REFERENCES disaster_thresholds(threshold_id)
                                ON DELETE SET NULL,

    -- USGS update tracking
    -- We do not keep full history (not an archive DB)
    -- but we track whether the initial estimate was revised
    initial_magnitude       DECIMAL(4,2),
    -- value when our system first saw this event
    magnitude_was_revised   BOOLEAN NOT NULL DEFAULT FALSE,
    usgs_last_updated_at    TIMESTAMPTZ,
    -- last time USGS updated this event record

    -- Timestamps
    earthquake_time         TIMESTAMPTZ NOT NULL,
    -- actual physical event time from USGS
    first_seen_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- when our system first detected this event
    last_refreshed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- when our system last wrote to this row

    raw_api_response        JSONB NOT NULL,
    -- full USGS feature JSON preserved for agent access

    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT seismic_magnitude_valid
        CHECK (magnitude BETWEEN -2.0 AND 10.0),
    CONSTRAINT seismic_depth_positive
        CHECK (depth_km IS NULL OR depth_km >= 0),
    CONSTRAINT seismic_significance_range
        CHECK (significance IS NULL
               OR significance BETWEEN 0 AND 1000),
    CONSTRAINT seismic_lat_pk_bounds
        CHECK (latitude  BETWEEN 23.0 AND 38.0),
    CONSTRAINT seismic_lon_pk_bounds
        CHECK (longitude BETWEEN 60.0 AND 78.0)
);

CREATE INDEX idx_seismic_coordinates
    ON seismic_events USING GIST(coordinates);

CREATE INDEX idx_seismic_earthquake_time
    ON seismic_events(earthquake_time DESC);

CREATE INDEX idx_seismic_magnitude_time
    ON seismic_events(magnitude DESC, earthquake_time DESC);

CREATE INDEX idx_seismic_province_time
    ON seismic_events(resolved_province, earthquake_time DESC)
    WHERE resolved_province IS NOT NULL;

CREATE INDEX idx_seismic_breach
    ON seismic_events(earthquake_time DESC)
    WHERE has_breach = TRUE;

CREATE INDEX idx_seismic_significant
    ON seismic_events(earthquake_time DESC)
    WHERE significance >= 500;

CREATE TRIGGER trg_seismic_updated_at
    BEFORE UPDATE ON seismic_events
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();


-- ============================================================================
-- TIME-SERIES TABLE 4: flood_gauge_current
--
-- CURRENT SITUATION ONLY.
-- Exactly ONE row per active gauge — always the most recent reading.
-- This is a true UPSERT where gauge_id is the primary key.
-- When a new reading arrives it OVERWRITES the previous row completely.
-- There is no history here — only NOW.
-- Maximum: 150 rows (one per gauge). Fixed size forever.
-- ============================================================================

CREATE TABLE flood_gauge_current (
    gauge_id                UUID PRIMARY KEY
                                REFERENCES flood_gauge_registry(gauge_id)
                                ON DELETE CASCADE,

    -- Denormalized for fast reads
    google_gauge_id         VARCHAR(100) NOT NULL,
    gauge_name              VARCHAR(255) NOT NULL,
    river_name              VARCHAR(255) NOT NULL,
    river_system            VARCHAR(100),
    district                VARCHAR(100),
    province                pk_province,

    -- Source tracking
    cycle_id                UUID REFERENCES collection_cycles(cycle_id)
                                ON DELETE SET NULL,

    -- ── CURRENT READING ───────────────────────────────────────────────────────
    reading_time            TIMESTAMPTZ NOT NULL,
    -- timestamp of the actual gauge measurement
    current_level_m         DECIMAL(8,3),

    -- ── THRESHOLD COMPARISON (computed at write time) ──────────────────────────
    -- copied from flood_gauge_registry at write time for fast access
    warning_level_m         DECIMAL(8,3),
    danger_level_m          DECIMAL(8,3),
    extreme_level_m         DECIMAL(8,3),

    pct_of_warning          DECIMAL(7,3),
    -- (current_level_m / warning_level_m) × 100
    pct_of_danger           DECIMAL(7,3),
    pct_of_historical_max   DECIMAL(7,3),

    -- ── TREND ANALYSIS (computed vs previous reading) ──────────────────────────
    previous_level_m        DECIMAL(8,3),
    -- the level from the reading that this one replaces
    level_change_m          DECIMAL(8,4),
    -- current minus previous
    rise_rate_m_per_hour    DECIMAL(8,4),
    river_trend             river_trend,
    hours_to_warning        DECIMAL(8,2),
    -- projected hours until warning level at current rise rate
    -- NULL if falling or already above warning
    hours_to_danger         DECIMAL(8,2),

    -- ── OFFICIAL CLASSIFICATION ────────────────────────────────────────────────
    flood_status            flood_status NOT NULL DEFAULT 'no_flooding',

    -- ── BREACH STATE ───────────────────────────────────────────────────────────
    has_breach              BOOLEAN NOT NULL DEFAULT FALSE,
    breach_severity         breach_level,
    threshold_id            UUID REFERENCES disaster_thresholds(threshold_id)
                                ON DELETE SET NULL,

    -- ── DATA PROVENANCE ────────────────────────────────────────────────────────
    raw_api_response        JSONB,
    collected_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- when our system wrote this row

    CONSTRAINT gauge_current_level_non_negative
        CHECK (current_level_m IS NULL OR current_level_m >= 0),
    CONSTRAINT gauge_current_pct_range
        CHECK (pct_of_warning IS NULL
               OR pct_of_warning BETWEEN 0 AND 1000)
    -- 1000% allows for catastrophic events
);

CREATE INDEX idx_flood_current_province
    ON flood_gauge_current(province)
    WHERE province IS NOT NULL;

CREATE INDEX idx_flood_current_breach
    ON flood_gauge_current(breach_severity)
    WHERE has_breach = TRUE;

CREATE INDEX idx_flood_current_status
    ON flood_gauge_current(flood_status)
    WHERE flood_status != 'no_flooding';

CREATE INDEX idx_flood_current_rising
    ON flood_gauge_current(river_trend)
    WHERE river_trend IN ('rising', 'rapidly_rising');


-- ============================================================================
-- TIME-SERIES TABLE 5: flood_gauge_forecasts
--
-- 5-DAY FORWARD PREDICTION WINDOW per gauge.
-- One row per gauge per forecast hour.
-- UPSERT on (gauge_id, forecast_for_datetime).
-- Maximum: 150 gauges × 120 hours = 18,000 rows. Fixed size.
--
-- DELETION: Daily cleanup deletes WHERE
--           DATE(forecast_for_datetime) < CURRENT_DATE
-- ============================================================================

CREATE TABLE flood_gauge_forecasts (
    gauge_id                UUID        NOT NULL
                                REFERENCES flood_gauge_registry(gauge_id)
                                ON DELETE CASCADE,
    forecast_for_datetime   TIMESTAMPTZ NOT NULL,
    -- the specific future hour this forecast row represents

    -- Computed
    forecast_date           DATE     NOT NULL,
    day_offset              SMALLINT NOT NULL,
    -- 0 = today, 1 = tomorrow ... 4
    forecast_horizon_h      INT      NOT NULL,
    -- hours from now until forecast_for_datetime

    -- Denormalized
    google_gauge_id         VARCHAR(100) NOT NULL,
    gauge_name              VARCHAR(255),
    river_name              VARCHAR(255) NOT NULL,
    district                VARCHAR(100),
    province                pk_province,

    -- Source
    cycle_id                UUID REFERENCES collection_cycles(cycle_id)
                                ON DELETE SET NULL,
    forecast_issued_at      TIMESTAMPTZ NOT NULL,
    -- when Google generated this forecast
    last_updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- ── PROBABILISTIC LEVEL FORECASTS ─────────────────────────────────────────
    level_p10_m             DECIMAL(8,3),
    -- 10th percentile (optimistic — only 10% chance level is below this)
    level_p50_m             DECIMAL(8,3),
    -- 50th percentile (median / most likely level)
    level_p90_m             DECIMAL(8,3),
    -- 90th percentile (pessimistic — 90% chance level is below this)

    -- ── EXCEEDANCE PROBABILITIES ───────────────────────────────────────────────
    prob_exceeds_warning_pct    DECIMAL(5,2),
    prob_exceeds_danger_pct     DECIMAL(5,2),
    prob_exceeds_extreme_pct    DECIMAL(5,2),

    -- ── CLASSIFICATION ────────────────────────────────────────────────────────
    forecast_status         flood_status NOT NULL DEFAULT 'no_flooding',
    -- based on p50 level
    worst_case_status       flood_status,
    -- based on p90 level

    -- ── BREACH ASSESSMENT ──────────────────────────────────────────────────────
    has_forecast_breach     BOOLEAN NOT NULL DEFAULT FALSE,
    breach_severity         breach_level,
    -- based on p50 vs danger threshold
    threshold_id            UUID REFERENCES disaster_thresholds(threshold_id)
                                ON DELETE SET NULL,

    raw_api_response        JSONB,

    PRIMARY KEY (gauge_id, forecast_for_datetime),

    CONSTRAINT flood_forecast_valid_after_issued
        CHECK (forecast_for_datetime > forecast_issued_at),
    CONSTRAINT flood_forecast_horizon_positive
        CHECK (forecast_horizon_h > 0),
    CONSTRAINT flood_forecast_probs_range
        CHECK (
            (prob_exceeds_warning_pct IS NULL
             OR prob_exceeds_warning_pct BETWEEN 0 AND 100)
        AND (prob_exceeds_danger_pct IS NULL
             OR prob_exceeds_danger_pct BETWEEN 0 AND 100)
        AND (prob_exceeds_extreme_pct IS NULL
             OR prob_exceeds_extreme_pct BETWEEN 0 AND 100)
        ),
    CONSTRAINT flood_forecast_day_offset_range
        CHECK (day_offset BETWEEN 0 AND 5)
);

CREATE INDEX idx_flood_forecast_gauge_datetime
    ON flood_gauge_forecasts(gauge_id, forecast_for_datetime);

CREATE INDEX idx_flood_forecast_breach
    ON flood_gauge_forecasts(forecast_for_datetime)
    WHERE has_forecast_breach = TRUE;

CREATE INDEX idx_flood_forecast_district_date
    ON flood_gauge_forecasts(district, forecast_date)
    WHERE has_forecast_breach = TRUE;

CREATE INDEX idx_flood_forecast_danger_prob
    ON flood_gauge_forecasts(gauge_id, forecast_for_datetime)
    WHERE prob_exceeds_danger_pct >= 30;


-- ============================================================================
-- ALERT OUTPUT TABLE: threshold_breach_log
--
-- Every threshold crossing detected by the collection service.
-- This is the OUTPUT of this database and the INPUT to the main
-- ClimaSync operational system's Verification Agent.
-- Rows here have breach_dispatch_status tracking to ensure
-- every breach reaches the main system exactly once.
--
-- DELETION: Delete WHERE detected_at < now() - INTERVAL '5 days'
--           and dispatch_status = 'dispatched'
-- ============================================================================

CREATE TABLE threshold_breach_log (
    breach_id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Which observation triggered this breach
    source_api              api_source_name NOT NULL,
    weather_location_id     UUID,
    weather_datetime        TIMESTAMPTZ,
    -- references weather_hourly_window(location_id, forecast_for_datetime)
    -- stored as separate columns because composite FK is not standard

    seismic_event_id        UUID REFERENCES seismic_events(event_id)
                                ON DELETE SET NULL,

    gauge_id                UUID REFERENCES flood_gauge_registry(gauge_id)
                                ON DELETE SET NULL,
    -- NULL for weather breaches
    is_forecast_breach      BOOLEAN NOT NULL DEFAULT FALSE,
    -- TRUE = the breach is in forecast data (future event warning)
    -- FALSE = breach in current observed data (happening now)
    forecast_horizon_h      INT,
    -- hours until the forecast breach materialises
    -- NULL if is_forecast_breach = FALSE

    -- Which threshold was crossed
    threshold_id            UUID NOT NULL
                                REFERENCES disaster_thresholds(threshold_id)
                                ON DELETE RESTRICT,
    disaster_kind           disaster_kind NOT NULL,
    metric_name             VARCHAR(100)  NOT NULL,

    -- Location context (denormalized for main system consumption)
    location_name           VARCHAR(255),
    district                VARCHAR(100),
    province                pk_province,
    latitude                DECIMAL(10,7),
    longitude               DECIMAL(10,7),
    coordinates             GEOGRAPHY(POINT, 4326),

    -- The breach itself
    observed_value          DECIMAL(12,4) NOT NULL,
    threshold_value         DECIMAL(12,4) NOT NULL,
    breach_severity         breach_level  NOT NULL,
    excess_amount           DECIMAL(12,4),
    -- observed_value minus threshold_value
    excess_pct              DECIMAL(8,4),
    -- (excess_amount / threshold_value) × 100

    -- Observation timestamp
    observation_time        TIMESTAMPTZ NOT NULL,

    -- Duplicate suppression
    -- If same location and same metric breached within suppression window
    -- the newer breach is marked as duplicate and NOT dispatched
    is_duplicate            BOOLEAN NOT NULL DEFAULT FALSE,
    duplicate_of_breach_id  UUID REFERENCES threshold_breach_log(breach_id)
                                ON DELETE SET NULL,
    suppression_window_used_m INT,
    -- how many minutes was the suppression window
    -- (configurable per metric — earthquake 60min, weather 180min)

    -- Dispatch tracking to main ClimaSync system
    dispatch_status         breach_dispatch_status NOT NULL DEFAULT 'pending',
    dispatched_at           TIMESTAMPTZ,
    main_system_alert_id    UUID,
    -- UUID of the alert created in the main ClimaSync database
    -- stored here for correlation
    dispatch_attempt_count  SMALLINT NOT NULL DEFAULT 0,
    last_dispatch_error     TEXT,

    detected_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT breach_excess_non_negative
        CHECK (excess_amount IS NULL OR excess_amount >= 0),
    CONSTRAINT breach_forecast_consistency
        CHECK (
            (is_forecast_breach = FALSE AND forecast_horizon_h IS NULL)
         OR (is_forecast_breach = TRUE  AND forecast_horizon_h > 0)
        ),
    CONSTRAINT breach_dispatch_attempts_non_negative
        CHECK (dispatch_attempt_count >= 0)
);

CREATE INDEX idx_breach_location_time
    ON threshold_breach_log(district, detected_at DESC)
    WHERE district IS NOT NULL;

CREATE INDEX idx_breach_kind_severity
    ON threshold_breach_log(disaster_kind, breach_severity, detected_at DESC);

CREATE INDEX idx_breach_pending_dispatch
    ON threshold_breach_log(detected_at ASC)
    WHERE dispatch_status = 'pending'
      AND is_duplicate = FALSE;

CREATE INDEX idx_breach_failed_dispatch
    ON threshold_breach_log(detected_at ASC)
    WHERE dispatch_status = 'dispatch_failed';

CREATE INDEX idx_breach_seismic
    ON threshold_breach_log(seismic_event_id)
    WHERE seismic_event_id IS NOT NULL;

CREATE INDEX idx_breach_gauge
    ON threshold_breach_log(gauge_id)
    WHERE gauge_id IS NOT NULL;

CREATE TRIGGER trg_breach_log_updated_at
    BEFORE UPDATE ON threshold_breach_log
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();


-- ============================================================================
-- TRIGGERS
-- ============================================================================

-- ── TRIGGER 1: Auto-classify earthquake magnitude ────────────────────────────

CREATE OR REPLACE FUNCTION compute_magnitude_class()
RETURNS TRIGGER AS $$
BEGIN
    NEW.magnitude_class := CASE
        WHEN NEW.magnitude <  2.0 THEN 'micro'
        WHEN NEW.magnitude <  4.0 THEN 'minor'
        WHEN NEW.magnitude <  5.0 THEN 'light'
        WHEN NEW.magnitude <  6.0 THEN 'moderate'
        WHEN NEW.magnitude <  7.0 THEN 'strong'
        WHEN NEW.magnitude <  8.0 THEN 'major'
        ELSE                           'great'
    END::magnitude_class;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_seismic_magnitude_class
    BEFORE INSERT OR UPDATE OF magnitude ON seismic_events
    FOR EACH ROW
    EXECUTE FUNCTION compute_magnitude_class();


-- ── TRIGGER 2: Auto-classify earthquake depth ────────────────────────────────

CREATE OR REPLACE FUNCTION compute_depth_class()
RETURNS TRIGGER AS $$
BEGIN
    NEW.depth_class := CASE
        WHEN NEW.depth_km IS NULL  THEN NULL
        WHEN NEW.depth_km <=  70   THEN 'shallow'
        WHEN NEW.depth_km <= 300   THEN 'intermediate'
        ELSE                            'deep'
    END::depth_class;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_seismic_depth_class
    BEFORE INSERT OR UPDATE OF depth_km ON seismic_events
    FOR EACH ROW
    EXECUTE FUNCTION compute_depth_class();


-- ── TRIGGER 3: Auto-decode WMO weather code to weather_condition ─────────────

CREATE OR REPLACE FUNCTION decode_wmo_code()
RETURNS TRIGGER AS $$
BEGIN
    NEW.weather_condition := CASE
        WHEN NEW.weather_code  = 0              THEN 'clear'
        WHEN NEW.weather_code IN (1, 2)         THEN 'partly_cloudy'
        WHEN NEW.weather_code  = 3              THEN 'overcast'
        WHEN NEW.weather_code IN (45, 48)       THEN 'fog'
        WHEN NEW.weather_code IN (51, 53, 55)   THEN 'drizzle'
        WHEN NEW.weather_code IN (56, 57)       THEN 'freezing_rain'
        WHEN NEW.weather_code IN (61, 63)       THEN 'rain'
        WHEN NEW.weather_code  = 65             THEN 'heavy_rain'
        WHEN NEW.weather_code IN (71, 73)       THEN 'snow'
        WHEN NEW.weather_code  = 75             THEN 'heavy_snow'
        WHEN NEW.weather_code  = 77             THEN 'snow'
        WHEN NEW.weather_code IN (80, 81)       THEN 'rain_showers'
        WHEN NEW.weather_code  = 82             THEN 'heavy_rain'
        WHEN NEW.weather_code IN (85, 86)       THEN 'snow_showers'
        WHEN NEW.weather_code  = 95             THEN 'thunderstorm'
        WHEN NEW.weather_code IN (96, 99)       THEN 'thunderstorm_with_hail'
        ELSE                                         'overcast'
    END::weather_condition;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_weather_decode_wmo
    BEFORE INSERT OR UPDATE OF weather_code ON weather_hourly_window
    FOR EACH ROW
    EXECUTE FUNCTION decode_wmo_code();


-- ── TRIGGER 4: Auto-compute wind cardinal direction ──────────────────────────

CREATE OR REPLACE FUNCTION compute_wind_cardinal()
RETURNS TRIGGER AS $$
BEGIN
    NEW.wind_direction_cardinal := CASE
        WHEN NEW.wind_direction_deg IS NULL   THEN NULL
        WHEN NEW.wind_direction_deg <   22.5  THEN 'N'
        WHEN NEW.wind_direction_deg <   67.5  THEN 'NE'
        WHEN NEW.wind_direction_deg <  112.5  THEN 'E'
        WHEN NEW.wind_direction_deg <  157.5  THEN 'SE'
        WHEN NEW.wind_direction_deg <  202.5  THEN 'S'
        WHEN NEW.wind_direction_deg <  247.5  THEN 'SW'
        WHEN NEW.wind_direction_deg <  292.5  THEN 'W'
        WHEN NEW.wind_direction_deg <  337.5  THEN 'NW'
        ELSE                                       'N'
    END;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_weather_wind_cardinal
    BEFORE INSERT OR UPDATE OF wind_direction_deg ON weather_hourly_window
    FOR EACH ROW
    EXECUTE FUNCTION compute_wind_cardinal();


-- ── TRIGGER 5: Auto-compute day_offset on weather_hourly_window ──────────────
-- day_offset = how many days from today is forecast_for_datetime

CREATE OR REPLACE FUNCTION compute_weather_day_offset()
RETURNS TRIGGER AS $$
BEGIN
    NEW.forecast_date := DATE(
        NEW.forecast_for_datetime AT TIME ZONE 'Asia/Karachi'
    );
    NEW.day_offset := (
        NEW.forecast_date - (now() AT TIME ZONE 'Asia/Karachi')::DATE
    )::SMALLINT;

    -- Reject rows outside the 6-day window
    IF NEW.day_offset < 0 OR NEW.day_offset > 5 THEN
        RAISE EXCEPTION
            'forecast_for_datetime % is outside the 6-day window. '
            'day_offset=% is not in range [0,5]',
            NEW.forecast_for_datetime, NEW.day_offset;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_weather_day_offset
    BEFORE INSERT OR UPDATE OF forecast_for_datetime ON weather_hourly_window
    FOR EACH ROW
    EXECUTE FUNCTION compute_weather_day_offset();


-- ── TRIGGER 6: Auto-compute day_offset on weather_daily_summaries ────────────

CREATE OR REPLACE FUNCTION compute_daily_summary_offset()
RETURNS TRIGGER AS $$
BEGIN
    NEW.day_offset := (NEW.summary_date - (now() AT TIME ZONE 'Asia/Karachi')::DATE)::SMALLINT;

    IF NEW.day_offset < 0 OR NEW.day_offset > 5 THEN
        RAISE EXCEPTION
            'summary_date % is outside 6-day window. day_offset=%',
            NEW.summary_date, NEW.day_offset;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_daily_summary_offset
    BEFORE INSERT OR UPDATE OF summary_date ON weather_daily_summaries
    FOR EACH ROW
    EXECUTE FUNCTION compute_daily_summary_offset();


-- ── TRIGGER 7: Auto-compute day_offset on flood_gauge_forecasts ──────────────

CREATE OR REPLACE FUNCTION compute_flood_forecast_offset()
RETURNS TRIGGER AS $$
BEGIN
    NEW.forecast_date  := DATE(
        NEW.forecast_for_datetime AT TIME ZONE 'Asia/Karachi'
    );
    NEW.day_offset     := (NEW.forecast_date - (now() AT TIME ZONE 'Asia/Karachi')::DATE)::SMALLINT;
    NEW.forecast_horizon_h := EXTRACT(
        EPOCH FROM (NEW.forecast_for_datetime - now())
    )::INT / 3600;

    IF NEW.day_offset < 0 OR NEW.day_offset > 5 THEN
        RAISE EXCEPTION
            'Flood forecast % is outside 6-day window. day_offset=%',
            NEW.forecast_for_datetime, NEW.day_offset;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_flood_forecast_offset
    BEFORE INSERT OR UPDATE OF forecast_for_datetime ON flood_gauge_forecasts
    FOR EACH ROW
    EXECUTE FUNCTION compute_flood_forecast_offset();


-- ── TRIGGER 8: Update pakistan_locations poll state after each poll ───────────

CREATE OR REPLACE FUNCTION sync_location_poll_state()
RETURNS TRIGGER AS $$
DECLARE
    v_interval INT;
BEGIN
    IF NEW.api_name = 'open_meteo' AND NEW.location_id IS NOT NULL THEN

        SELECT poll_interval_minutes
        INTO   v_interval
        FROM   pakistan_locations
        WHERE  location_id = NEW.location_id;

        IF NEW.status = 'success' THEN
            UPDATE pakistan_locations SET
                last_polled_at       = NEW.polled_at,
                last_poll_outcome    = 'success',
                next_poll_due_at     = NEW.polled_at
                                       + (v_interval || ' minutes')::INTERVAL,
                consecutive_failures = 0,
                updated_at           = now()
            WHERE location_id = NEW.location_id;
        ELSE
            UPDATE pakistan_locations SET
                last_poll_outcome    = NEW.status,
                consecutive_failures = consecutive_failures + 1,
                updated_at           = now()
            WHERE location_id = NEW.location_id;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Note: This trigger references a location_poll_log table.
-- location_poll_log is a lightweight operational log
-- defined below as part of collection_cycles support.


-- ── TRIGGER 9: Update api_registry health after cycle completion ──────────────

CREATE OR REPLACE FUNCTION sync_api_health_on_cycle()
RETURNS TRIGGER AS $$
BEGIN
    -- Only sync when a cycle transitions to a terminal state
    IF NEW.status IN ('completed', 'partial', 'failed')
       AND OLD.status = 'running' THEN

        UPDATE api_registry SET
            current_health      = CASE
                WHEN NEW.status = 'completed' THEN 'healthy'
                WHEN NEW.status = 'partial'   THEN 'degraded'
                WHEN NEW.status = 'failed'    THEN
                    CASE WHEN consecutive_failures + 1 >= 3
                         THEN 'down'::api_health_state
                         ELSE 'degraded'::api_health_state
                    END
            END,
            last_success_at     = CASE
                WHEN NEW.status = 'completed' THEN NEW.completed_at
                ELSE last_success_at
            END,
            last_failure_at     = CASE
                WHEN NEW.status = 'failed' THEN NEW.completed_at
                ELSE last_failure_at
            END,
            consecutive_failures = CASE
                WHEN NEW.status = 'completed' THEN 0
                ELSE consecutive_failures + 1
            END,
            avg_latency_ms      = CASE
                WHEN NEW.avg_latency_ms IS NOT NULL
                THEN COALESCE(avg_latency_ms, NEW.avg_latency_ms) * 0.7
                     + NEW.avg_latency_ms * 0.3
                -- exponential moving average with 0.3 weight on new value
                ELSE avg_latency_ms
            END,
            updated_at          = now()
        WHERE api_id = NEW.api_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_sync_api_health_on_cycle
    AFTER UPDATE OF status ON collection_cycles
    FOR EACH ROW
    EXECUTE FUNCTION sync_api_health_on_cycle();


-- ── TRIGGER 10: Mark seismic row as magnitude_was_revised on magnitude update ─

CREATE OR REPLACE FUNCTION track_magnitude_revision()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.magnitude IS DISTINCT FROM NEW.magnitude THEN
        -- First time magnitude changes: save original
        IF NOT OLD.magnitude_was_revised THEN
            NEW.initial_magnitude    := OLD.magnitude;
            NEW.magnitude_was_revised := TRUE;
        END IF;
        NEW.last_refreshed_at := now();
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_seismic_track_revision
    BEFORE UPDATE OF magnitude ON seismic_events
    FOR EACH ROW
    EXECUTE FUNCTION track_magnitude_revision();


-- ============================================================================
-- CLEANUP FUNCTION
-- Called once per day by a scheduled PostgreSQL cron job
-- (pg_cron extension) or by the collection service at startup.
-- Implements the rolling 5-day window by deleting expired rows.
-- ============================================================================

CREATE OR REPLACE FUNCTION cleanup_expired_window_data()
RETURNS TABLE (
    table_name      TEXT,
    rows_deleted    BIGINT,
    cleanup_time    TIMESTAMPTZ
) AS $$
DECLARE
    v_weather_deleted   BIGINT;
    v_daily_deleted     BIGINT;
    v_seismic_deleted   BIGINT;
    v_flood_f_deleted   BIGINT;
    v_breach_deleted    BIGINT;
    v_cutoff_date       DATE := CURRENT_DATE;
    v_breach_cutoff     TIMESTAMPTZ := now() - INTERVAL '5 days';
BEGIN
    -- 1. Delete expired weather hourly rows
    --    Any row whose forecast date is before today
    DELETE FROM weather_hourly_window
    WHERE forecast_date < v_cutoff_date;
    GET DIAGNOSTICS v_weather_deleted = ROW_COUNT;

    -- 2. Delete expired weather daily summaries
    DELETE FROM weather_daily_summaries
    WHERE summary_date < v_cutoff_date;
    GET DIAGNOSTICS v_daily_deleted = ROW_COUNT;

    -- 3. Delete expired seismic events
    --    Events older than 5 days from their earthquake_time
    DELETE FROM seismic_events
    WHERE DATE(earthquake_time) < v_cutoff_date - INTERVAL '4 days';
    GET DIAGNOSTICS v_seismic_deleted = ROW_COUNT;

    -- 4. Delete expired flood forecasts
    DELETE FROM flood_gauge_forecasts
    WHERE forecast_date < v_cutoff_date;
    GET DIAGNOSTICS v_flood_f_deleted = ROW_COUNT;

    -- 5. Delete old dispatched breach log entries
    --    Keep undispatched ones regardless of age
    DELETE FROM threshold_breach_log
    WHERE detected_at < v_breach_cutoff
      AND dispatch_status = 'dispatched';
    GET DIAGNOSTICS v_breach_deleted = ROW_COUNT;

    -- Return summary
    RETURN QUERY VALUES
        ('weather_hourly_window',    v_weather_deleted,  now()),
        ('weather_daily_summaries',  v_daily_deleted,    now()),
        ('seismic_events',           v_seismic_deleted,  now()),
        ('flood_gauge_forecasts',    v_flood_f_deleted,  now()),
        ('threshold_breach_log',     v_breach_deleted,   now());
END;
$$ LANGUAGE plpgsql;

-- Schedule with pg_cron (run at 00:05 UTC daily)
-- SELECT cron.schedule(
--     'daily-window-cleanup',
--     '5 0 * * *',
--     $$SELECT * FROM cleanup_expired_window_data()$$
-- );


-- ============================================================================
-- VIEWS
-- ============================================================================

-- ── VIEW 1: current_weather_per_location ─────────────────────────────────────
-- Most recent observed hour per location (day_offset = 0, current hour)
-- Used by frontend map to render temperature and condition overlays

CREATE VIEW current_weather_per_location AS
SELECT DISTINCT ON (w.location_id)
    w.location_id,
    w.location_key,
    w.location_name,
    w.district,
    w.province,
    w.latitude,
    w.longitude,
    w.forecast_for_datetime     AS current_hour,
    w.last_updated_at,

    -- Temperature
    w.temp_c,
    w.temp_apparent_c,
    w.temp_dewpoint_c,

    -- Precipitation
    w.precip_mm,
    w.precip_prob_pct,
    w.precip_24h_mm,
    w.precip_72h_mm,

    -- Wind
    w.wind_speed_kmh,
    w.wind_gusts_kmh,
    w.wind_direction_cardinal,

    -- Atmospheric
    w.humidity_pct,
    w.pressure_hpa,
    w.visibility_m,
    w.uv_index,
    w.cape_jkg,

    -- Classification
    w.weather_condition,
    w.weather_description,
    w.is_daytime,

    -- Flags
    w.flag_extreme_heat,
    w.flag_heatwave,
    w.flag_heavy_rain,
    w.flag_very_heavy_rain,
    w.flag_storm,
    w.flag_severe_storm,
    w.flag_cold_wave,
    w.flag_dust_storm,
    w.flag_dense_fog,

    -- Breach
    w.has_breach,
    w.breach_severity,
    w.breach_metric,
    w.breach_observed_value,

    -- Location risk profile from parent table
    pl.population,
    pl.flood_risk_zone,
    pl.heat_risk_zone,
    pl.seismic_zone,
    pl.infrastructure_quality,
    pl.drainage_quality,

    -- Data freshness indicator
    EXTRACT(EPOCH FROM (now() - w.last_updated_at)) / 60
        AS data_age_minutes,
    CASE
        WHEN now() - w.last_updated_at < INTERVAL '3 hours'  THEN 'fresh'
        WHEN now() - w.last_updated_at < INTERVAL '6 hours'  THEN 'stale'
        ELSE                                                       'very_stale'
    END AS data_freshness

FROM weather_hourly_window w
JOIN pakistan_locations pl ON pl.location_id = w.location_id
WHERE w.day_offset = 0
  AND w.forecast_for_datetime <= now()
ORDER BY w.location_id, w.forecast_for_datetime DESC;


-- ── VIEW 2: weather_5day_forecast_per_location ───────────────────────────────
-- Daily summary for each location across all 5 days
-- Used by frontend forecast panel and Risk Analysis Agent

CREATE VIEW weather_5day_forecast_per_location AS
SELECT
    d.location_id,
    d.location_key,
    d.location_name,
    d.district,
    d.province,
    d.summary_date,
    d.day_offset,
    CASE d.day_offset
        WHEN 0 THEN 'Today'
        WHEN 1 THEN 'Tomorrow'
        ELSE to_char(d.summary_date, 'Day')
    END AS day_label,

    d.temp_max_c,
    d.temp_min_c,
    d.feels_like_max_c,
    d.precip_total_mm,
    d.precip_prob_max_pct,
    d.wind_speed_max_kmh,
    d.wind_gusts_max_kmh,
    d.uv_index_max,
    d.dominant_condition,
    d.sunrise_at,
    d.sunset_at,

    d.flag_extreme_heat_day,
    d.flag_heatwave_day,
    d.flag_heavy_rain_day,
    d.flag_storm_day,
    d.flag_cold_wave_day,
    d.worst_breach_severity,

    d.last_updated_at

FROM weather_daily_summaries d
ORDER BY d.location_id, d.day_offset;


-- ── VIEW 3: significant_recent_earthquakes ───────────────────────────────────
-- All M4.0+ events in the 5-day window not marked as deleted
-- Primary seismic situational awareness view

CREATE VIEW significant_recent_earthquakes AS
SELECT
    s.event_id,
    s.usgs_event_id,
    s.magnitude,
    s.magnitude_type,
    s.magnitude_class,
    s.depth_km,
    s.depth_class,
    s.latitude,
    s.longitude,
    s.usgs_place,
    s.resolved_district,
    s.resolved_province,
    s.distance_to_nearest_km,
    s.felt_reports,
    s.cdi,
    s.mmi,
    s.tsunami_flag,
    s.usgs_alert_level,
    s.significance,
    s.data_quality,
    s.has_breach,
    s.breach_severity,
    s.magnitude_was_revised,
    s.earthquake_time,
    s.first_seen_at,
    s.last_refreshed_at,

    -- Hours since event
    ROUND(
        EXTRACT(EPOCH FROM (now() - s.earthquake_time)) / 3600, 1
    ) AS hours_since_event,

    -- Nearest location context
    pl.location_name        AS nearest_location,
    pl.population           AS nearest_population,
    pl.seismic_zone,
    pl.infrastructure_quality,
    pl.building_stock,

    -- Breach log reference
    tbl.breach_id,
    tbl.dispatch_status     AS breach_dispatch_status

FROM seismic_events s
LEFT JOIN pakistan_locations pl
    ON pl.location_id = s.nearest_location_id
LEFT JOIN threshold_breach_log tbl
    ON tbl.seismic_event_id = s.event_id
WHERE
    s.magnitude    >= 4.0
    AND s.data_quality != 'deleted'
ORDER BY s.earthquake_time DESC;


-- ── VIEW 4: flood_situation_current ──────────────────────────────────────────
-- Current state of every active flood gauge with context
-- Real-time flood operational dashboard

CREATE VIEW flood_situation_current AS
SELECT
    fc.gauge_id,
    fc.google_gauge_id,
    fc.gauge_name,
    fc.river_name,
    fc.river_system,
    fc.district,
    fc.province,

    -- Current reading
    fc.reading_time,
    fc.current_level_m,
    fc.warning_level_m,
    fc.danger_level_m,
    fc.extreme_level_m,
    fc.pct_of_warning,
    fc.pct_of_danger,
    fc.pct_of_historical_max,

    -- Trend
    fc.previous_level_m,
    fc.level_change_m,
    fc.rise_rate_m_per_hour,
    fc.river_trend,
    fc.hours_to_warning,
    fc.hours_to_danger,

    -- Status
    fc.flood_status,
    fc.has_breach,
    fc.breach_severity,

    -- Data freshness
    EXTRACT(EPOCH FROM (now() - fc.reading_time)) / 60
        AS reading_age_minutes,
    CASE
        WHEN now() - fc.reading_time < INTERVAL '1 hour'  THEN 'fresh'
        WHEN now() - fc.reading_time < INTERVAL '6 hours' THEN 'stale'
        ELSE                                                    'very_stale'
    END AS data_freshness,

    -- Static gauge context
    gr.historical_max_m,
    gr.bankfull_level_m,
    gr.basin_name,
    gr.upstream_area_sqkm,
    gr.poll_priority,

    -- Nearest city population at risk
    pl.location_name        AS nearest_city,
    pl.population           AS population_at_risk,

    -- 24-hour probabilistic forecast (p50 median)
    ff24.level_p50_m        AS forecast_24h_level_p50,
    ff24.level_p90_m        AS forecast_24h_level_p90,
    ff24.prob_exceeds_danger_pct  AS forecast_24h_danger_prob_pct,
    ff24.forecast_status    AS forecast_24h_status,
    ff24.worst_case_status  AS forecast_24h_worst_case,

    -- 72-hour probabilistic forecast (p50 median)
    ff72.level_p50_m        AS forecast_72h_level_p50,
    ff72.prob_exceeds_danger_pct  AS forecast_72h_danger_prob_pct

FROM flood_gauge_current fc
JOIN flood_gauge_registry gr ON gr.gauge_id = fc.gauge_id
LEFT JOIN pakistan_locations pl
    ON pl.location_id = gr.nearest_location_id

-- Nearest forecast to the 24-hour mark
LEFT JOIN LATERAL (
    SELECT
        ff.level_p50_m,
        ff.level_p90_m,
        ff.prob_exceeds_danger_pct,
        ff.forecast_status,
        ff.worst_case_status
    FROM flood_gauge_forecasts ff
    WHERE ff.gauge_id = fc.gauge_id
      AND ff.forecast_horizon_h BETWEEN 22 AND 26
    ORDER BY ABS(ff.forecast_horizon_h - 24)
    LIMIT 1
) ff24 ON TRUE

-- Nearest forecast to the 72-hour mark
LEFT JOIN LATERAL (
    SELECT
        ff.level_p50_m,
        ff.prob_exceeds_danger_pct
    FROM flood_gauge_forecasts ff
    WHERE ff.gauge_id = fc.gauge_id
      AND ff.forecast_horizon_h BETWEEN 70 AND 74
    ORDER BY ABS(ff.forecast_horizon_h - 72)
    LIMIT 1
) ff72 ON TRUE

WHERE gr.is_active = TRUE
ORDER BY
    CASE fc.breach_severity
        WHEN 'extreme'   THEN 1
        WHEN 'emergency' THEN 2
        WHEN 'warning'   THEN 3
        WHEN 'watch'     THEN 4
        ELSE                  5
    END,
    fc.pct_of_danger DESC NULLS LAST;


-- ── VIEW 5: active_breach_summary ────────────────────────────────────────────
-- All currently active threshold breaches across all data sources
-- Ordered by severity then recency
-- Primary input feed for the Verification Agent in main system

CREATE VIEW active_breach_summary AS
SELECT
    tbl.breach_id,
    tbl.source_api,
    tbl.disaster_kind,
    tbl.metric_name,
    tbl.location_name,
    tbl.district,
    tbl.province,
    tbl.latitude,
    tbl.longitude,
    tbl.observed_value,
    tbl.threshold_value,
    tbl.breach_severity,
    tbl.excess_amount,
    tbl.excess_pct,
    tbl.observation_time,
    tbl.is_forecast_breach,
    tbl.forecast_horizon_h,
    tbl.dispatch_status,
    tbl.detected_at,

    -- Threshold context
    dt.watch_threshold,
    dt.warning_threshold,
    dt.emergency_threshold,
    dt.extreme_threshold,
    dt.unit,
    dt.breach_direction,
    dt.applies_season,

    -- Location vulnerability context
    pl.population,
    pl.flood_risk_zone,
    pl.heat_risk_zone,
    pl.seismic_zone,
    pl.infrastructure_quality,
    pl.drainage_quality,

    -- Seconds this breach has been waiting for dispatch
    EXTRACT(EPOCH FROM (now() - tbl.detected_at))
        AS seconds_since_detection

FROM threshold_breach_log tbl
LEFT JOIN disaster_thresholds dt
    ON dt.threshold_id = tbl.threshold_id
LEFT JOIN pakistan_locations pl
    ON pl.location_id = tbl.weather_location_id

WHERE tbl.is_duplicate    = FALSE
  AND tbl.dispatch_status IN ('pending', 'dispatch_failed')

ORDER BY
    CASE tbl.breach_severity
        WHEN 'extreme'   THEN 1
        WHEN 'emergency' THEN 2
        WHEN 'warning'   THEN 3
        WHEN 'watch'     THEN 4
    END,
    tbl.detected_at ASC;


-- ── VIEW 6: pakistan_risk_heatmap ─────────────────────────────────────────────
-- One row per active monitoring location with composite risk score
-- Drives the frontend interactive risk map

CREATE VIEW pakistan_risk_heatmap AS
SELECT
    pl.location_id,
    pl.location_key,
    pl.location_name,
    pl.district,
    pl.province,
    pl.latitude,
    pl.longitude,
    pl.population,
    pl.flood_risk_zone,
    pl.seismic_zone,
    pl.heat_risk_zone,
    pl.infrastructure_quality,

    -- Current weather state
    cw.temp_c,
    cw.temp_apparent_c,
    cw.precip_24h_mm,
    cw.wind_speed_kmh,
    cw.humidity_pct,
    cw.weather_condition,
    cw.has_breach           AS weather_breach,
    cw.breach_severity      AS weather_breach_severity,
    cw.data_freshness,

    -- Worst upcoming weather in 5-day window
    ww.worst_breach_severity AS worst_upcoming_weather_breach,
    ww.worst_breach_date,
    ww.worst_precip_day,

    -- Nearest significant earthquake (last 5 days)
    ne.magnitude            AS nearest_eq_magnitude,
    ne.magnitude_class      AS nearest_eq_class,
    ne.earthquake_time      AS nearest_eq_time,
    ne.breach_severity      AS seismic_breach_severity,
    ne.distance_km          AS nearest_eq_distance_km,

    -- Nearest flood gauge status
    nf.flood_status         AS nearest_gauge_status,
    nf.pct_of_danger        AS nearest_gauge_pct_danger,
    nf.river_trend          AS nearest_gauge_trend,
    nf.breach_severity      AS flood_breach_severity,
    nf.river_name           AS nearest_river,

    -- Composite risk score (0 = normal, 4 = extreme)
    GREATEST(
        CASE cw.breach_severity
            WHEN 'extreme'   THEN 4
            WHEN 'emergency' THEN 3
            WHEN 'warning'   THEN 2
            WHEN 'watch'     THEN 1
            ELSE                  0
        END,
        CASE ne.breach_severity
            WHEN 'extreme'   THEN 4
            WHEN 'emergency' THEN 3
            WHEN 'warning'   THEN 2
            WHEN 'watch'     THEN 1
            ELSE                  0
        END,
        CASE nf.breach_severity
            WHEN 'extreme'   THEN 4
            WHEN 'emergency' THEN 3
            WHEN 'warning'   THEN 2
            WHEN 'watch'     THEN 1
            ELSE                  0
        END
    ) AS composite_risk_score,

    -- Human readable label
    CASE GREATEST(
        CASE cw.breach_severity
            WHEN 'extreme' THEN 4 WHEN 'emergency' THEN 3
            WHEN 'warning' THEN 2 WHEN 'watch'     THEN 1 ELSE 0
        END,
        CASE ne.breach_severity
            WHEN 'extreme' THEN 4 WHEN 'emergency' THEN 3
            WHEN 'warning' THEN 2 WHEN 'watch'     THEN 1 ELSE 0
        END,
        CASE nf.breach_severity
            WHEN 'extreme' THEN 4 WHEN 'emergency' THEN 3
            WHEN 'warning' THEN 2 WHEN 'watch'     THEN 1 ELSE 0
        END
    )
        WHEN 4 THEN 'EXTREME'
        WHEN 3 THEN 'EMERGENCY'
        WHEN 2 THEN 'WARNING'
        WHEN 1 THEN 'WATCH'
        ELSE        'NORMAL'
    END AS composite_risk_label

FROM pakistan_locations pl

-- Current weather
LEFT JOIN current_weather_per_location cw
    ON cw.location_id = pl.location_id

-- Worst upcoming weather across the 5-day window
LEFT JOIN LATERAL (
    SELECT
        MAX(CASE worst_breach_severity
            WHEN 'extreme' THEN 4 WHEN 'emergency' THEN 3
            WHEN 'warning' THEN 2 WHEN 'watch'     THEN 1 ELSE 0
        END) AS worst_score,
        MAX(worst_breach_severity)  AS worst_breach_severity,
        MIN(CASE WHEN worst_breach_severity IS NOT NULL
                 THEN summary_date END) AS worst_breach_date,
        MAX(precip_total_mm)        AS worst_precip_day
    FROM weather_daily_summaries
    WHERE location_id = pl.location_id
      AND day_offset  > 0
) ww ON TRUE

-- Nearest significant earthquake
LEFT JOIN LATERAL (
    SELECT
        s.magnitude,
        s.magnitude_class,
        s.earthquake_time,
        s.breach_severity,
        ST_Distance(s.coordinates, pl.coordinates) / 1000 AS distance_km
    FROM seismic_events s
    WHERE s.data_quality != 'deleted'
      AND s.magnitude    >= 4.0
    ORDER BY s.coordinates <-> pl.coordinates
    LIMIT 1
) ne ON TRUE

-- Nearest flood gauge
LEFT JOIN LATERAL (
    SELECT
        fc.flood_status,
        fc.pct_of_danger,
        fc.river_trend,
        fc.breach_severity,
        fc.river_name
    FROM flood_gauge_current fc
    JOIN flood_gauge_registry gr ON gr.gauge_id = fc.gauge_id
    ORDER BY gr.coordinates <-> pl.coordinates
    LIMIT 1
) nf ON TRUE

WHERE pl.is_active = TRUE;


-- ── VIEW 7: collection_health_dashboard ──────────────────────────────────────
-- Real-time health of all three APIs and their most recent cycle
-- Used by admin monitoring panel

CREATE VIEW collection_health_dashboard AS
SELECT
    ar.api_id,
    ar.api_name,
    ar.display_name,
    ar.current_health,
    ar.last_success_at,
    ar.last_failure_at,
    ar.consecutive_failures,
    ar.avg_latency_ms,
    ar.calls_in_window,
    ar.max_requests_per_minute,

    -- Backoff state
    ar.backoff_until,
    CASE WHEN ar.backoff_until > now() THEN TRUE ELSE FALSE END
        AS is_in_backoff,
    GREATEST(0, EXTRACT(EPOCH FROM (ar.backoff_until - now())))::INT
        AS backoff_remaining_seconds,

    -- Minutes since last successful data collection
    ROUND(
        EXTRACT(EPOCH FROM (now() - ar.last_success_at)) / 60
    )::INT AS minutes_since_last_success,

    -- Most recent cycle stats
    lc.cycle_id             AS last_cycle_id,
    lc.status               AS last_cycle_status,
    lc.started_at           AS last_cycle_started,
    lc.completed_at         AS last_cycle_completed,
    lc.duration_ms          AS last_cycle_duration_ms,
    lc.locations_targeted,
    lc.locations_success,
    lc.locations_failed,
    CASE WHEN lc.locations_targeted > 0
         THEN ROUND(
             lc.locations_success::DECIMAL / lc.locations_targeted * 100, 1
         )
         ELSE NULL
    END                     AS last_cycle_success_rate_pct,
    lc.rows_upserted,
    lc.rows_inserted,
    lc.breaches_triggered   AS last_cycle_breaches,
    lc.rate_limit_hits      AS last_cycle_rate_limit_hits

FROM api_registry ar
LEFT JOIN LATERAL (
    SELECT
        cycle_id, status, started_at, completed_at,
        duration_ms, locations_targeted, locations_success,
        locations_failed, rows_upserted, rows_inserted,
        breaches_triggered, rate_limit_hits
    FROM collection_cycles
    WHERE api_id = ar.api_id
    ORDER BY started_at DESC
    LIMIT 1
) lc ON TRUE
WHERE ar.is_active = TRUE
ORDER BY ar.api_name;


-- ── VIEW 8: undispatched_breaches ────────────────────────────────────────────
-- Ordered queue of breach alerts not yet sent to main ClimaSync system
-- Polled by the dispatch service every 30 seconds

CREATE VIEW undispatched_breaches AS
SELECT
    tbl.breach_id,
    tbl.source_api,
    tbl.disaster_kind,
    tbl.metric_name,
    tbl.location_name,
    tbl.district,
    tbl.province,
    tbl.latitude,
    tbl.longitude,
    tbl.coordinates,
    tbl.observed_value,
    tbl.threshold_value,
    tbl.breach_severity,
    tbl.excess_amount,
    tbl.excess_pct,
    tbl.observation_time,
    tbl.is_forecast_breach,
    tbl.forecast_horizon_h,
    tbl.dispatch_attempt_count,
    tbl.last_dispatch_error,
    tbl.detected_at,

    -- Threshold detail
    dt.unit,
    dt.breach_direction,
    dt.watch_threshold,
    dt.warning_threshold,
    dt.emergency_threshold,
    dt.extreme_threshold,

    -- Payload ready for main system API call
    jsonb_build_object(
        'breach_id',           tbl.breach_id,
        'source_api',          tbl.source_api,
        'disaster_kind',       tbl.disaster_kind,
        'metric_name',         tbl.metric_name,
        'location_name',       tbl.location_name,
        'district',            tbl.district,
        'province',            tbl.province,
        'latitude',            tbl.latitude,
        'longitude',           tbl.longitude,
        'observed_value',      tbl.observed_value,
        'threshold_value',     tbl.threshold_value,
        'breach_severity',     tbl.breach_severity,
        'unit',                dt.unit,
        'observation_time',    tbl.observation_time,
        'is_forecast',         tbl.is_forecast_breach,
        'forecast_horizon_h',  tbl.forecast_horizon_h,
        'detected_at',         tbl.detected_at
    ) AS dispatch_payload

FROM threshold_breach_log tbl
LEFT JOIN disaster_thresholds dt ON dt.threshold_id = tbl.threshold_id
WHERE
    tbl.is_duplicate    = FALSE
    AND tbl.dispatch_status IN ('pending', 'dispatch_failed')
ORDER BY
    CASE tbl.breach_severity
        WHEN 'extreme'   THEN 1
        WHEN 'emergency' THEN 2
        WHEN 'warning'   THEN 3
        WHEN 'watch'     THEN 4
    END,
    tbl.detected_at ASC;


-- ============================================================================
-- DONE
-- ============================================================================