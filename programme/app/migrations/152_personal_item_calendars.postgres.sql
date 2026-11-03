-- Apply to align_owner and every align_tester_* schema before Build 156-v40.
ALTER TABLE personal_items
    ADD COLUMN IF NOT EXISTS calendar_id TEXT NOT NULL DEFAULT '';
ALTER TABLE personal_items
    ADD COLUMN IF NOT EXISTS calendar_event_id INTEGER;
INSERT INTO schema_migrations(migration_id, applied_at)
VALUES ('152_personal_item_calendars', CURRENT_TIMESTAMP)
ON CONFLICT (migration_id) DO NOTHING;
