-- Existing hosted databases. Apply once per Owner schema and each tester schema.
-- Idempotent. The running application does not apply this file.
CREATE TABLE IF NOT EXISTS align_owner.work_rota_imports (
    id text PRIMARY KEY,
    status text NOT NULL CHECK (status IN ('processing','review','partially_imported','imported','failed','cancelled')),
    source_file_count integer NOT NULL DEFAULT 0 CHECK (source_file_count >= 0),
    candidate_count integer NOT NULL DEFAULT 0 CHECK (candidate_count >= 0),
    created_count integer NOT NULL DEFAULT 0 CHECK (created_count >= 0),
    skipped_count integer NOT NULL DEFAULT 0 CHECK (skipped_count >= 0),
    error_code text NOT NULL DEFAULT '',
    notice_codes text NOT NULL DEFAULT '[]',
    created_at text NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at text NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at text
);

CREATE TABLE IF NOT EXISTS align_owner.work_rota_entries (
    id text PRIMARY KEY,
    import_id text NOT NULL REFERENCES align_owner.work_rota_imports(id) ON DELETE CASCADE,
    work_date text,
    source_date_text text NOT NULL DEFAULT '',
    start_time text NOT NULL DEFAULT '',
    end_time text NOT NULL DEFAULT '',
    shift_label text NOT NULL DEFAULT '',
    department text NOT NULL DEFAULT '',
    location_id bigint REFERENCES align_owner.locations(id) ON DELETE SET NULL,
    location_text text NOT NULL DEFAULT '',
    shift_type_id bigint REFERENCES align_owner.shift_types(id) ON DELETE SET NULL,
    template_id bigint REFERENCES align_owner.shift_templates(id) ON DELETE SET NULL,
    entry_kind text NOT NULL DEFAULT 'unknown' CHECK (entry_kind IN ('shift','day_off','leave','sickness','unknown')),
    confidence double precision NOT NULL DEFAULT 0 CHECK (confidence >= 0 AND confidence <= 1),
    review_status text NOT NULL DEFAULT 'pending' CHECK (review_status IN ('pending','approved','rejected','imported')),
    created_shift_id bigint,
    created_leave_id bigint,
    duplicate_shift_id bigint,
    ambiguity text NOT NULL DEFAULT '',
    approvable integer NOT NULL DEFAULT 0 CHECK (approvable IN (0, 1)),
    fingerprint text NOT NULL DEFAULT '',
    published_snapshot text NOT NULL DEFAULT '',
    revision integer NOT NULL DEFAULT 1 CHECK (revision >= 1),
    created_at text NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at text NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_work_rota_entries_import_status ON align_owner.work_rota_entries(import_id, review_status);
CREATE INDEX IF NOT EXISTS idx_work_rota_entries_fingerprint ON align_owner.work_rota_entries(fingerprint);
CREATE UNIQUE INDEX IF NOT EXISTS idx_work_rota_entries_shift ON align_owner.work_rota_entries(created_shift_id);

ALTER TABLE align_owner.shifts ADD COLUMN IF NOT EXISTS source_import_entry_id text;
CREATE UNIQUE INDEX IF NOT EXISTS idx_shifts_source_import_entry ON align_owner.shifts(source_import_entry_id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'shifts_source_import_entry_fk'
          AND conrelid = 'align_owner.shifts'::regclass
    ) THEN
        ALTER TABLE align_owner.shifts
            ADD CONSTRAINT shifts_source_import_entry_fk
            FOREIGN KEY (source_import_entry_id)
            REFERENCES align_owner.work_rota_entries(id)
            ON DELETE RESTRICT;
    END IF;
END $$;

INSERT INTO align_owner.schema_migrations(migration_id, applied_at)
VALUES ('157_work_rota_import', CURRENT_TIMESTAMP)
ON CONFLICT(migration_id) DO NOTHING;
