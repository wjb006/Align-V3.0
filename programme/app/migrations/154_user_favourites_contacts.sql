-- Explicit, idempotent migration for retained Contacts and Favourites features.
-- Existing runtime-created tables and rows are preserved by IF NOT EXISTS.
CREATE TABLE IF NOT EXISTS user_favourites (
    id INTEGER PRIMARY KEY AUTOINCREMENT, entity_type TEXT NOT NULL, entity_key TEXT NOT NULL,
    label TEXT NOT NULL, value TEXT NOT NULL DEFAULT '', metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(entity_type, entity_key)
);
CREATE INDEX IF NOT EXISTS idx_user_favourites_type_updated ON user_favourites(entity_type, updated_at DESC);
CREATE TABLE IF NOT EXISTS align_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, address TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL, UNIQUE(name,address,phone)
);
