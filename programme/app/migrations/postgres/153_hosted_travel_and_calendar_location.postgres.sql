-- Apply explicitly to align_owner and each align_tester_* schema before enabling hosted Travel.
-- This is a reviewed deployment migration, never an application-startup operation.
ALTER TABLE calendar_events ADD COLUMN IF NOT EXISTS location TEXT NOT NULL DEFAULT '';
CREATE TABLE IF NOT EXISTS transport_preferences (
    id INTEGER PRIMARY KEY CHECK (id=1),
    arrival_buffer INTEGER NOT NULL DEFAULT 10 CHECK (arrival_buffer BETWEEN 0 AND 120),
    modes TEXT NOT NULL DEFAULT '["bus","rail","walk"]',
    home_lat DOUBLE PRECISION,
    home_lon DOUBLE PRECISION
);
INSERT INTO transport_preferences(id) VALUES (1) ON CONFLICT(id) DO NOTHING;
INSERT INTO calendar_sync_state(id,revision,modified_at) VALUES (1,0,CURRENT_TIMESTAMP) ON CONFLICT(id) DO NOTHING;
INSERT INTO icloud_config(id,instance_id) VALUES (1,md5(random()::text || clock_timestamp()::text)) ON CONFLICT(id) DO NOTHING;
CREATE TABLE IF NOT EXISTS transport_journey_cache (
    event_key TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
INSERT INTO schema_migrations(migration_id, applied_at)
VALUES ('153_hosted_travel_and_calendar_location', CURRENT_TIMESTAMP)
ON CONFLICT (migration_id) DO NOTHING;
