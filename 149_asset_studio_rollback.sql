PRAGMA foreign_keys = OFF;
BEGIN IMMEDIATE;
DROP TRIGGER IF EXISTS asset_category_default_active_insert; DROP TRIGGER IF EXISTS asset_category_default_active_update; DROP TRIGGER IF EXISTS asset_activate_variant; DROP TRIGGER IF EXISTS asset_activate_usage; DROP TRIGGER IF EXISTS asset_activate_variant_insert; DROP TRIGGER IF EXISTS asset_activate_usage_insert;
DROP INDEX IF EXISTS idx_assets_type_status; DROP INDEX IF EXISTS idx_assets_category; DROP INDEX IF EXISTS idx_assets_active_type; DROP INDEX IF EXISTS idx_assets_display_name; DROP INDEX IF EXISTS idx_assets_content_sha256; DROP INDEX IF EXISTS idx_asset_variants_asset; DROP INDEX IF EXISTS idx_asset_variants_hash; DROP INDEX IF EXISTS idx_asset_usage_enabled; DROP INDEX IF EXISTS idx_asset_categories_group; DROP INDEX IF EXISTS idx_asset_categories_display_name; DROP INDEX IF EXISTS idx_asset_audit_asset_date; DROP INDEX IF EXISTS idx_asset_audit_actor_date;
DROP TABLE IF EXISTS asset_audit_log; DROP TABLE IF EXISTS asset_usage_rules; DROP TABLE IF EXISTS asset_variants; DROP TABLE IF EXISTS assets; DROP TABLE IF EXISTS asset_categories;
DELETE FROM schema_migrations WHERE migration_id='149_asset_studio';
COMMIT;
PRAGMA foreign_keys = ON;
