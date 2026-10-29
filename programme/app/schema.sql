-- Legacy SQLite compatibility schema for existing databases that already contain schedule tables.
-- New local databases must use schema_v3.sqlite.sql; never use this file to initialise a fresh V3 database.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS settings (
    setting_key TEXT PRIMARY KEY,
    setting_value TEXT NOT NULL
);

-- These records define the Settings menu presented in the User app.  Admin can
-- add information-only branches as well as control the standard branches.
CREATE TABLE IF NOT EXISTS menu_branches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch_key TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    icon TEXT NOT NULL DEFAULT '○',
    branch_type TEXT NOT NULL DEFAULT 'note',
    content TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    sort_order INTEGER NOT NULL DEFAULT 100
);

CREATE INDEX IF NOT EXISTS idx_menu_branches_order ON menu_branches(active, sort_order, title);

-- Top-level items on the User home screen (the Parent Menu in the diagram).
CREATE TABLE IF NOT EXISTS parent_menu_branches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch_key TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    icon TEXT NOT NULL DEFAULT '○',
    destination TEXT NOT NULL DEFAULT 'note',
    content TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    sort_order INTEGER NOT NULL DEFAULT 100,
    parent_id INTEGER REFERENCES parent_menu_branches(id) ON DELETE SET NULL,
    colour TEXT NOT NULL DEFAULT '#365CE6',
    locked INTEGER NOT NULL DEFAULT 0 CHECK (locked IN (0, 1)),
    optional INTEGER NOT NULL DEFAULT 1 CHECK (optional IN (0, 1))
);

CREATE INDEX IF NOT EXISTS idx_parent_menu_order ON parent_menu_branches(active, parent_id, sort_order, title);

-- User-created Home sections turn Align into a broader organiser rather than a
-- work-only planner. A section may be linked to one iCloud calendar for
-- two-way import/export while remaining usable as a local Align section.
CREATE TABLE IF NOT EXISTS organiser_sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    icon TEXT NOT NULL DEFAULT '•',
    colour TEXT NOT NULL DEFAULT '#365CE6',
    calendar_url TEXT NOT NULL DEFAULT '',
    calendar_name TEXT NOT NULL DEFAULT '',
    import_enabled INTEGER NOT NULL DEFAULT 1 CHECK (import_enabled IN (0, 1)),
    export_enabled INTEGER NOT NULL DEFAULT 1 CHECK (export_enabled IN (0, 1)),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    sort_order INTEGER NOT NULL DEFAULT 100,
    parent_branch_id INTEGER REFERENCES parent_menu_branches(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_organiser_sections_order ON organiser_sections(active, sort_order, name);

-- Calendar connections are independent of section storage so section layout
-- migrations can change without losing CalDAV URL ownership.
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
CREATE INDEX IF NOT EXISTS idx_calendar_links_target ON calendar_links(target_kind, target_key);

CREATE TABLE IF NOT EXISTS organiser_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    section_id INTEGER NOT NULL REFERENCES organiser_sections(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    start_at TEXT NOT NULL,
    end_at TEXT NOT NULL,
    all_day INTEGER NOT NULL DEFAULT 0 CHECK (all_day IN (0, 1)),
    location TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    request_id TEXT UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_organiser_events_section_time ON organiser_events(section_id, start_at, end_at);

CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    address TEXT NOT NULL DEFAULT '',
    colour TEXT NOT NULL DEFAULT '#365CE6',
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS shift_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    colour TEXT NOT NULL DEFAULT '#3B82F6',
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

-- Categories (for example Wards and Clinic) that are offered at each work
-- location.  Saved shift patterns then provide the actual AM/PM hours.
CREATE TABLE IF NOT EXISTS location_shift_types (
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    shift_type_id INTEGER NOT NULL REFERENCES shift_types(id) ON DELETE CASCADE,
    PRIMARY KEY (location_id, shift_type_id)
);

CREATE TABLE IF NOT EXISTS shift_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    shift_type_id INTEGER NOT NULL REFERENCES shift_types(id) ON DELETE RESTRICT,
    label TEXT NOT NULL,
    sub_shift_type TEXT NOT NULL DEFAULT '',
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    break_minutes INTEGER NOT NULL DEFAULT 0 CHECK (break_minutes >= 0),
    applicable_days TEXT NOT NULL DEFAULT '[]',
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    UNIQUE(location_id, label)
);

CREATE TABLE IF NOT EXISTS shifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_date TEXT NOT NULL,
    template_id INTEGER REFERENCES shift_templates(id) ON DELETE SET NULL,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    shift_type_id INTEGER REFERENCES shift_types(id) ON DELETE SET NULL,
    location_name TEXT NOT NULL,
    shift_type_name TEXT NOT NULL,
    colour TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    break_minutes INTEGER NOT NULL DEFAULT 0,
    hours REAL NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_shifts_date ON shifts(work_date);
CREATE INDEX IF NOT EXISTS idx_shifts_template ON shifts(template_id);

-- A repeated Confirm request must not create the week twice after a timeout.
CREATE TABLE IF NOT EXISTS shift_batches (
    request_id TEXT PRIMARY KEY,
    payload_hash TEXT NOT NULL,
    result_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS annual_leave (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    leave_date TEXT NOT NULL UNIQUE,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_leave_date ON annual_leave(leave_date);

-- Imported calendars are read-only sources used to spot clashes. They never
-- become Align shifts unless the user deliberately creates a shift.
CREATE TABLE IF NOT EXISTS calendar_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    source_kind TEXT NOT NULL DEFAULT 'ics_import',
    section_id INTEGER REFERENCES organiser_sections(id) ON DELETE CASCADE,
    target_kind TEXT NOT NULL DEFAULT '',
    target_key TEXT NOT NULL DEFAULT '',
    source_key TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS calendar_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL REFERENCES calendar_sources(id) ON DELETE CASCADE,
    event_uid TEXT NOT NULL,
    location TEXT NOT NULL DEFAULT '',
    start_at TEXT NOT NULL,
    end_at TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    all_day INTEGER NOT NULL DEFAULT 0 CHECK (all_day IN (0, 1)),
    UNIQUE(source_id, event_uid)
);

CREATE INDEX IF NOT EXISTS idx_calendar_events_start ON calendar_events(start_at, end_at);

-- No Apple email or password is stored. Account hash prevents linking an old
-- event map to a different account. IDs persist across server restarts.
CREATE TABLE IF NOT EXISTS icloud_config (
    id INTEGER PRIMARY KEY CHECK(id=1), instance_id TEXT NOT NULL DEFAULT '',
    account_hash TEXT NOT NULL DEFAULT '', target_url TEXT NOT NULL DEFAULT '',
    read_urls TEXT NOT NULL DEFAULT '[]'
);
INSERT OR IGNORE INTO icloud_config(id) VALUES(1);
CREATE TABLE IF NOT EXISTS icloud_items (
    local_key TEXT PRIMARY KEY, uid TEXT NOT NULL UNIQUE, url TEXT NOT NULL,
    etag TEXT NOT NULL, content_hash TEXT NOT NULL
);

-- Alerts are created alongside shifts when notifications are enabled. They can
-- be surfaced in the app and included in an exported calendar file.
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shift_id INTEGER NOT NULL REFERENCES shifts(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    alert_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
);

CREATE INDEX IF NOT EXISTS idx_alerts_time ON alerts(alert_at, status);

CREATE TABLE IF NOT EXISTS alert_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    minutes_before INTEGER NOT NULL CHECK (minutes_before BETWEEN 0 AND 10080),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

-- Stable revisions let calendar subscribers recognise changes without
-- generating a different event identifier on each refresh.
CREATE TABLE IF NOT EXISTS calendar_sync_state (
    id INTEGER PRIMARY KEY CHECK (id=1),
    revision INTEGER NOT NULL DEFAULT 0,
    modified_at TEXT NOT NULL
);
INSERT OR IGNORE INTO calendar_sync_state(id,modified_at)
VALUES(1,strftime('%Y%m%dT%H%M%SZ','now'));
