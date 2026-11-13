-- Two-step sign-in columns and the short-lived password challenge.
-- Additive. Apply to align_auth only. The application does not run this file.
ALTER TABLE align_auth.beta_users ADD COLUMN IF NOT EXISTS totp_secret TEXT NOT NULL DEFAULT '';
ALTER TABLE align_auth.beta_users ADD COLUMN IF NOT EXISTS totp_enabled INTEGER NOT NULL DEFAULT 0;
CREATE TABLE IF NOT EXISTS align_auth.beta_login_challenges (
    challenge_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    expires BIGINT NOT NULL,
    created_at BIGINT NOT NULL
);
INSERT INTO align_owner.schema_migrations(migration_id, applied_at)
VALUES ('159_account_security', CURRENT_TIMESTAMP)
ON CONFLICT(migration_id) DO NOTHING;
