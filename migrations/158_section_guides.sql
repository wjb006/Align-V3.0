-- Guided section setup: saved places, labels, defaults and event details.
-- CREATE IF NOT EXISTS only, so a fresh database and an existing one can both apply it.
CREATE TABLE IF NOT EXISTS saved_places (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    section_id INTEGER REFERENCES organiser_sections(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_saved_places_section ON saved_places(section_id, LOWER(name), LOWER(location));

CREATE TABLE IF NOT EXISTS planner_labels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    colour TEXT NOT NULL DEFAULT '#16D9F2',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_planner_labels_name ON planner_labels(LOWER(name));

CREATE TABLE IF NOT EXISTS section_defaults (
    section_id INTEGER PRIMARY KEY REFERENCES organiser_sections(id) ON DELETE CASCADE,
    place_id INTEGER REFERENCES saved_places(id) ON DELETE SET NULL,
    travel_minutes INTEGER NOT NULL DEFAULT 30 CHECK (travel_minutes BETWEEN 0 AND 10080),
    travel_mode TEXT NOT NULL DEFAULT 'transit',
    travel_info TEXT NOT NULL DEFAULT '',
    leave_alert_minutes INTEGER NOT NULL DEFAULT 0 CHECK (leave_alert_minutes BETWEEN 0 AND 10080),
    reminder_minutes INTEGER NOT NULL DEFAULT 0 CHECK (reminder_minutes BETWEEN 0 AND 10080)
);

CREATE TABLE IF NOT EXISTS organiser_event_details (
    event_id INTEGER PRIMARY KEY REFERENCES organiser_events(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL DEFAULT 'Event',
    label_name TEXT NOT NULL DEFAULT '',
    place_id INTEGER REFERENCES saved_places(id) ON DELETE SET NULL
);
