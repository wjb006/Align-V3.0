-- Provision the shared HERE transit allowance in the auth schema.
SET search_path TO align_auth, align_owner;
-- Apply with search_path=align_auth,align_owner; the marker is stored with owner migrations.
-- Runtime requests reserve quota but never create or alter schema.
CREATE TABLE IF NOT EXISTS align_here_transit_usage (
    requested_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_align_here_transit_usage_requested_at
    ON align_here_transit_usage(requested_at);
INSERT INTO schema_migrations(migration_id, applied_at)
VALUES ('155_here_transit_usage', CURRENT_TIMESTAMP)
ON CONFLICT(migration_id) DO NOTHING;
