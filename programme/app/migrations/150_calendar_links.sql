CREATE TABLE IF NOT EXISTS calendar_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_kind TEXT NOT NULL,
    target_key TEXT NOT NULL,
    calendar_url TEXT NOT NULL,
    calendar_name TEXT NOT NULL DEFAULT '',
    import_enabled INTEGER NOT NULL DEFAULT 1 CHECK (import_enabled IN (0, 1)),
    export_enabled INTEGER NOT NULL DEFAULT 1 CHECK (export_enabled IN (0, 1)),
    UNIQUE(target_kind, target_key)
);
CREATE INDEX IF NOT EXISTS idx_calendar_links_target
    ON calendar_links(target_kind, target_key);
