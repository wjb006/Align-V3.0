CREATE TABLE IF NOT EXISTS transport_preferences (id INTEGER PRIMARY KEY CHECK(id=1), arrival_buffer INTEGER NOT NULL DEFAULT 10 CHECK(arrival_buffer BETWEEN 0 AND 120), modes TEXT NOT NULL DEFAULT '["bus","rail","walk"]', home_lat REAL, home_lon REAL);
INSERT OR IGNORE INTO transport_preferences(id) VALUES(1);
-- Build 146 shipped a different transport_cache schema. Keep that table and
-- its rows intact; Build 149 journey payloads use their own table.
CREATE TABLE IF NOT EXISTS transport_journey_cache (event_key TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL, expires_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_transport_journey_cache_expiry ON transport_journey_cache(expires_at);
