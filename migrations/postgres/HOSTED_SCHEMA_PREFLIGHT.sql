-- READ-ONLY preflight for migrations/postgres/fresh_v3_schema.sql.
-- Run against the dedicated V3 database after explicit provisioning.
-- First result: every row is a schema violation; expected result is no rows.
-- The restored shift planner is part of the required V3 schema; this check never mutates data.

WITH required_tables(schema_name, table_name) AS (
    VALUES
      ('align_auth','beta_users'), ('align_auth','beta_sessions'),
      ('align_auth','beta_invites'), ('align_auth','beta_password_resets'),
      ('align_auth','beta_idempotency'), ('align_auth','beta_audit_events'),
      ('align_auth','beta_rate_events'), ('align_auth','beta_feedback'),
      ('align_auth','beta_email_settings'), ('align_auth','beta_icloud_credentials'),
      ('align_auth','align_here_transit_usage'),
      ('align_owner','settings'), ('align_owner','personal_items'),
      ('align_owner','calendar_sources'), ('align_owner','calendar_events'),
      ('align_owner','organiser_sections'), ('align_owner','organiser_events'),
      ('align_owner','locations'), ('align_owner','shift_types'),
      ('align_owner','location_shift_types'), ('align_owner','shift_templates'),
      ('align_owner','shifts'), ('align_owner','shift_batches'),
      ('align_owner','annual_leave'), ('align_owner','alerts'), ('align_owner','alert_rules'),
      ('align_owner','parent_menu_branches'), ('align_owner','menu_branches'),
      ('align_owner','builder_config'), ('align_owner','builder_records'),
      ('align_owner','calendar_links'), ('align_owner','section_defs'),
      ('align_owner','section_fields'), ('align_owner','calendar_sync_state'),
      ('align_owner','icloud_config'), ('align_owner','icloud_items'),
      ('align_owner','schema_migrations'), ('align_owner','assets'),
      ('align_owner','asset_categories'), ('align_owner','asset_variants'),
      ('align_owner','asset_usage_rules'), ('align_owner','asset_audit_log'),
      ('align_owner','transport_preferences'), ('align_owner','transport_journey_cache'),
      ('align_owner','user_favourites'), ('align_owner','align_contacts')
)
SELECT 'missing required table: ' || r.schema_name || '.' || r.table_name AS check_name,
       1 AS violations
FROM required_tables r
WHERE NOT EXISTS (
    SELECT 1 FROM information_schema.tables t
    WHERE t.table_schema=r.schema_name AND t.table_name=r.table_name
      AND t.table_type='BASE TABLE'
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
)
UNION ALL
SELECT 'missing required column: align_owner.calendar_events.location', 1
WHERE NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='align_owner' AND table_name='calendar_events' AND column_name='location'
)
UNION ALL
SELECT 'missing required column: align_auth.align_here_transit_usage.requested_at', 1
WHERE NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='align_auth' AND table_name='align_here_transit_usage' AND column_name='requested_at'
)
UNION ALL
SELECT 'missing required column: align_owner.transport_preferences.' || c.column_name, 1
FROM (VALUES ('arrival_buffer'), ('modes'), ('home_lat'), ('home_lon')) AS c(column_name)
WHERE NOT EXISTS (
    SELECT 1 FROM information_schema.columns i
    WHERE i.table_schema='align_owner' AND i.table_name='transport_preferences' AND i.column_name=c.column_name
);

-- Every required migration marker should appear exactly once.
SELECT m.migration_id, COUNT(sm.migration_id)::bigint AS applied_count
FROM (VALUES ('149_asset_studio'), ('149_transport'), ('150_calendar_links'),
             ('151_sections'), ('152_personal_item_calendars'),
             ('153_hosted_travel_and_calendar_location'), ('154_user_favourites_contacts'), ('155_here_transit_usage'), ('156_shift_planner')) AS m(migration_id)
LEFT JOIN align_owner.schema_migrations sm ON sm.migration_id=m.migration_id
GROUP BY m.migration_id
ORDER BY m.migration_id;

-- Data baselines for later before/after redeploy comparison. owner_count must be one.
SELECT 'owner_count' AS metric, COUNT(*)::bigint AS value
FROM align_auth.beta_users WHERE is_owner=1
UNION ALL
SELECT 'personal_items_count', COUNT(*)::bigint FROM align_owner.personal_items
UNION ALL
SELECT 'sections_count', COUNT(*)::bigint FROM align_owner.organiser_sections
UNION ALL
SELECT 'section_fields_count', COUNT(*)::bigint FROM align_owner.section_fields
UNION ALL
SELECT 'legacy_table_' || legacy.table_name,
       CASE WHEN t.table_name IS NULL THEN 0 ELSE 1 END::bigint
FROM (VALUES ('shifts'), ('shift_templates'), ('shift_types'), ('locations'),
             ('location_shift_types'), ('annual_leave'), ('alert_rules'), ('alerts'),
             ('shift_batches')) AS legacy(table_name)
LEFT JOIN information_schema.tables t
  ON t.table_schema='align_owner' AND t.table_name=legacy.table_name
ORDER BY metric;
