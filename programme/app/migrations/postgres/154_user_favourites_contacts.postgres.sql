-- Explicit, idempotent provisioning for retained Contacts and Favourites APIs.
-- Run with align_owner (or a tester schema) on search_path. Never applied at request time.
CREATE TABLE IF NOT EXISTS align_contacts (
    id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, address TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL, UNIQUE(name,address,phone)
);
CREATE TABLE IF NOT EXISTS user_favourites (
    id BIGSERIAL PRIMARY KEY, entity_type TEXT NOT NULL, entity_key TEXT NOT NULL,
    label TEXT NOT NULL, value TEXT NOT NULL DEFAULT '', metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(entity_type, entity_key)
);
CREATE INDEX IF NOT EXISTS idx_user_favourites_type_updated ON user_favourites(entity_type, updated_at DESC);
INSERT INTO schema_migrations(migration_id, applied_at)
VALUES ('154_user_favourites_contacts', CURRENT_TIMESTAMP)
ON CONFLICT(migration_id) DO NOTHING;
