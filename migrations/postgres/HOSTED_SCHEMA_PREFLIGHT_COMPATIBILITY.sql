-- READ-ONLY compatibility-schema preflight for an existing legacy installation.
-- This deliberately expects legacy schedule tables and records their row counts.
-- Do not use for a fresh V3 schema. Never drop tables merely to make this pass.
-- No statements in this file create, alter, delete or update data.

WITH required_tables(schema_name, table_name) AS (
    VALUES
      ('align_auth','beta_users'),
      ('align_auth','beta_sessions'),
      ('align_auth','beta_invites'),
      ('align_auth','beta_password_resets'),
      ('align_auth','beta_idempotency'),
      ('align_auth','beta_audit_events'),
      ('align_auth','beta_rate_events'),
      ('align_auth','beta_feedback'),
      ('align_auth','beta_email_settings'),
      ('align_auth','beta_icloud_credentials'),
      ('align_owner','settings'),
      ('align_owner','personal_items'),
      ('align_owner','shifts'),
      ('align_owner','shift_templates'),
      ('align_owner','locations'),
      ('align_owner','shift_types'),
      ('align_owner','location_shift_types'),
      ('align_owner','annual_leave'),
      ('align_owner','alert_rules'),
      ('align_owner','alerts'),
      ('align_owner','calendar_sources'),
      ('align_owner','calendar_events'),
      ('align_owner','organiser_sections'),
      ('align_owner','organiser_events'),
      ('align_owner','parent_menu_branches'),
      ('align_owner','menu_branches'),
      ('align_owner','builder_config'),
      ('align_owner','builder_records'),
      ('align_owner','calendar_links'),
      ('align_owner','section_defs'),
      ('align_owner','section_fields'),
      ('align_owner','calendar_sync_state'),
      ('align_owner','icloud_config'),
      ('align_owner','icloud_items'),
      ('align_owner','shift_batches'),
      ('align_owner','schema_migrations'),
      ('align_owner','assets'),
      ('align_owner','asset_categories'),
      ('align_owner','asset_variants'),
      ('align_owner','asset_usage_rules'),
      ('align_owner','asset_audit_log')
)
SELECT 'missing required table: ' || r.schema_name || '.' || r.table_name AS check_name,
       1 AS violations
FROM required_tables r
WHERE NOT EXISTS (
    SELECT 1
    FROM information_schema.tables t
    WHERE t.table_schema = r.schema_name
      AND t.table_name = r.table_name
      AND t.table_type = 'BASE TABLE'
)
UNION ALL
SELECT 'missing required column: align_auth.beta_users.' || c.column_name, 1
FROM (VALUES ('user_id'), ('is_owner'), ('password_hash'), ('password_set_at'), ('created_at')) AS c(column_name)
WHERE NOT EXISTS (
    SELECT 1 FROM information_schema.columns i
    WHERE i.table_schema='align_auth' AND i.table_name='beta_users' AND i.column_name=c.column_name
)
UNION ALL
SELECT 'missing required column: align_owner.personal_items.' || c.column_name, 1
FROM (VALUES ('id'), ('kind'), ('title'), ('calendar_id'), ('calendar_event_id'), ('done'), ('created_at')) AS c(column_name)
WHERE NOT EXISTS (
    SELECT 1 FROM information_schema.columns i
    WHERE i.table_schema='align_owner' AND i.table_name='personal_items' AND i.column_name=c.column_name
);

-- Run these follow-up checks only after the first query returns no rows.
-- Every migration marker should appear exactly once. This query assumes the
-- schema_migrations table has already passed the metadata check above.
SELECT m.migration_id, COUNT(sm.migration_id)::bigint AS applied_count
FROM (VALUES ('149_asset_studio'), ('149_transport'), ('150_calendar_links'),
             ('151_sections'), ('152_personal_item_calendars')) AS m(migration_id)
LEFT JOIN align_owner.schema_migrations sm ON sm.migration_id=m.migration_id
GROUP BY m.migration_id
ORDER BY m.migration_id;

-- Data baselines for a later before/after redeploy comparison; counts need not
-- be zero. owner_count must equal exactly one. Never reset Owner credentials as
-- a workaround for a failed verification.
SELECT 'owner_count' AS metric, COUNT(*)::bigint AS value
FROM align_auth.beta_users WHERE is_owner=1
UNION ALL
SELECT 'personal_items_count', COUNT(*)::bigint FROM align_owner.personal_items
UNION ALL
SELECT 'legacy_shifts_count_preserve_until_review', COUNT(*)::bigint FROM align_owner.shifts
UNION ALL
SELECT 'legacy_shift_templates_count_preserve_until_review', COUNT(*)::bigint FROM align_owner.shift_templates
UNION ALL
SELECT 'sections_count', COUNT(*)::bigint FROM align_owner.organiser_sections
UNION ALL
SELECT 'section_fields_count', COUNT(*)::bigint FROM align_owner.section_fields;
