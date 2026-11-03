-- Local SQLite rota-import tables. The shifts provenance column is added by
-- migration_runner because schema_v3.sqlite.sql is reapplied on startup and an
-- unconditional ALTER would fail the second time.
CREATE TABLE IF NOT EXISTS work_rota_imports (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('processing','review','partially_imported','imported','failed','cancelled')),
    source_file_count INTEGER NOT NULL DEFAULT 0 CHECK (source_file_count >= 0),
    candidate_count INTEGER NOT NULL DEFAULT 0 CHECK (candidate_count >= 0),
    created_count INTEGER NOT NULL DEFAULT 0 CHECK (created_count >= 0),
    skipped_count INTEGER NOT NULL DEFAULT 0 CHECK (skipped_count >= 0),
    error_code TEXT NOT NULL DEFAULT '',
    notice_codes TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS work_rota_entries (
    id TEXT PRIMARY KEY,
    import_id TEXT NOT NULL REFERENCES work_rota_imports(id) ON DELETE CASCADE,
    work_date TEXT,
    source_date_text TEXT NOT NULL DEFAULT '',
    start_time TEXT NOT NULL DEFAULT '',
    end_time TEXT NOT NULL DEFAULT '',
    shift_label TEXT NOT NULL DEFAULT '',
    department TEXT NOT NULL DEFAULT '',
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    location_text TEXT NOT NULL DEFAULT '',
    shift_type_id INTEGER REFERENCES shift_types(id) ON DELETE SET NULL,
    template_id INTEGER REFERENCES shift_templates(id) ON DELETE SET NULL,
    entry_kind TEXT NOT NULL DEFAULT 'unknown' CHECK (entry_kind IN ('shift','day_off','leave','sickness','unknown')),
    confidence REAL NOT NULL DEFAULT 0 CHECK (confidence >= 0 AND confidence <= 1),
    review_status TEXT NOT NULL DEFAULT 'pending' CHECK (review_status IN ('pending','approved','rejected','imported')),
    created_shift_id INTEGER,
    created_leave_id INTEGER,
    duplicate_shift_id INTEGER,
    ambiguity TEXT NOT NULL DEFAULT '',
    approvable INTEGER NOT NULL DEFAULT 0 CHECK (approvable IN (0, 1)),
    fingerprint TEXT NOT NULL DEFAULT '',
    published_snapshot TEXT NOT NULL DEFAULT '',
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_work_rota_entries_import_status ON work_rota_entries(import_id, review_status);
CREATE INDEX IF NOT EXISTS idx_work_rota_entries_fingerprint ON work_rota_entries(fingerprint);
CREATE UNIQUE INDEX IF NOT EXISTS idx_work_rota_entries_shift ON work_rota_entries(created_shift_id) WHERE created_shift_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS work_rota_approvals (
    import_id TEXT NOT NULL REFERENCES work_rota_imports(id) ON DELETE CASCADE,
    idempotency_key TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (import_id, idempotency_key)
);
