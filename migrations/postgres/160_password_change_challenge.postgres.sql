-- Lets a breached password be replaced before a session is created.
-- Additive. Apply to align_auth after migration 159. The application does not run this file.
ALTER TABLE align_auth.beta_login_challenges
    ADD COLUMN IF NOT EXISTS purpose TEXT NOT NULL DEFAULT 'totp';
INSERT INTO align_owner.schema_migrations(migration_id, applied_at)
VALUES ('160_password_change_challenge', CURRENT_TIMESTAMP)
ON CONFLICT(migration_id) DO NOTHING;
