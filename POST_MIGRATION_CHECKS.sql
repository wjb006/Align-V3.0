SELECT (SELECT COUNT(*) FROM schema_migrations WHERE migration_id='149_asset_studio') AS migration_marker;
SELECT (SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name IN ('asset_categories','assets','asset_variants','asset_usage_rules','asset_audit_log')) AS asset_tables;
SELECT (SELECT COUNT(*) FROM asset_categories WHERE category_group='workplace' AND built_in=1) AS workplace_builtins;
SELECT (SELECT COUNT(*) FROM asset_categories WHERE category_group='event_type' AND built_in=1) AS event_type_builtins;
SELECT (SELECT COUNT(*) FROM asset_categories WHERE category_group='place' AND built_in=1) AS place_builtins;
SELECT (SELECT COUNT(*) FROM asset_categories WHERE category_group='travel' AND built_in=1) AS travel_builtins;
