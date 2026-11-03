CREATE TABLE IF NOT EXISTS transport_places (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_key TEXT NOT NULL DEFAULT '', label TEXT NOT NULL,
  latitude REAL, longitude REAL, provider TEXT NOT NULL DEFAULT 'manual', provider_id TEXT NOT NULL DEFAULT '',
  privacy_mode TEXT NOT NULL DEFAULT 'coarse', updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(user_key, provider, provider_id)
);
CREATE TABLE IF NOT EXISTS transport_cache (
  cache_key TEXT PRIMARY KEY, user_key TEXT NOT NULL DEFAULT '', payload TEXT NOT NULL,
  provider TEXT NOT NULL, fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at TEXT NOT NULL, etag TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS transport_queries (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_key TEXT NOT NULL DEFAULT '', origin_label TEXT NOT NULL,
  destination_label TEXT NOT NULL, depart_at TEXT, arrive_by TEXT, modes TEXT NOT NULL DEFAULT 'bus,rail,walk',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_transport_cache_expiry ON transport_cache(expires_at);
