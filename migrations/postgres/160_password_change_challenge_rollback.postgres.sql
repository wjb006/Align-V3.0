-- Reverse migration 160. Unfinished password-change challenges are removed with the column.
ALTER TABLE align_auth.beta_login_challenges DROP COLUMN IF EXISTS purpose;
DELETE FROM align_owner.schema_migrations WHERE migration_id='160_password_change_challenge';
