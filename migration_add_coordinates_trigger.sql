-- migration_add_coordinates_trigger.sql

CREATE OR REPLACE FUNCTION sync_seismic_coordinates()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.latitude IS NOT NULL AND NEW.longitude IS NOT NULL THEN
        NEW.coordinates := ST_SetSRID(ST_MakePoint(NEW.longitude::float8, NEW.latitude::float8), 4326);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_seismic_coordinates ON seismic_events;
CREATE TRIGGER trg_seismic_coordinates
    BEFORE INSERT OR UPDATE OF latitude, longitude ON seismic_events
    FOR EACH ROW
    EXECUTE FUNCTION sync_seismic_coordinates();
