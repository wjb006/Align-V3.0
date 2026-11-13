-- Reverse migration 159. Drops two-step secrets and unfinished challenges.
-- Do not run this while an owner still needs the authenticator to sign in.
DROP TABLE IF EXISTS align_auth.beta_login_challenges;
ALTER TABLE align_auth.beta_users DROP COLUMN IF EXISTS totp_enabled;
ALTER TABLE align_auth.beta_users DROP COLUMN IF EXISTS totp_secret;
DELETE FROM align_owner.schema_migrations WHERE migration_id='159_account_security';
