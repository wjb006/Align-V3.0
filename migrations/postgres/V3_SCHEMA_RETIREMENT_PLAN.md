# Align V3.0 fresh-schema and legacy schedule retirement plan

**Status:** planning baseline; not an applied migration.  
**Safety rule:** do not drop, truncate, rename, or overwrite existing schedule tables/data as part of V3.0 launch preparation.

## Why this is a release gate

The user-facing V3 flow has retired the schedule endpoints, but the source and hosted schema are not yet shift-free. A fresh V3 database cannot safely be declared ready while startup still expects shift-era tables. The current PostgreSQL bootstrap is a metadata-only fixture copied from the previous schema, not a production provisioning migration.

Verified current dependencies:
- `app.py::initialise_database_at` calls `postgres_support.validate_planner()` in PostgreSQL mode. In SQLite mode it still creates schedule-change triggers, migrates `shift_templates`, seeds Work/shift menu entries, and invokes `rebuild_shift_alerts()`.
- `postgres_support.py::validate_planner()` currently queries `shifts`, `shift_templates`, `locations`, `shift_types`, `location_shift_types`, `annual_leave`, `alert_rules`, `alerts`, and `shift_batches` in addition to V3 organiser, calendar, personal-item, and Studio tables.
- `admin_api.py` imports shift-pattern and location-category helpers from `work_setup.py`; these are legacy management surfaces and must be disconnected from active routes before the fresh schema can omit their tables.
- Existing regression `test_retired_shift_api.py` proves schedule endpoints return 404 and that SQLite reinitialisation retains legacy shift/leave rows. Keep and extend that data-preservation guarantee.
- The old schedule table family includes `locations`, `shift_types`, `location_shift_types`, `shift_templates`, `shifts`, `shift_batches`, `annual_leave`, `alert_rules`, and `alerts`. Some are connected by foreign keys, so dropping them individually is unsafe.

## Target table families

### Keep in a fresh V3 schema

- Account/authentication: `beta_users`, `beta_sessions`, invites, password resets, idempotency, audit/rate events, email settings and encrypted integration credentials.
- Personal organiser: `settings`, `personal_items`, `menu_branches`, `parent_menu_branches`, `organiser_sections`, `organiser_events`, `calendar_links`, `calendar_sources`, `calendar_events`, `calendar_sync_state`, `icloud_config`, `icloud_items`.
- Configurable Studio/database forms: `builder_config`, `builder_records`, `section_defs`, `section_fields`.
- Asset Studio: `assets`, `asset_categories`, `asset_variants`, `asset_usage_rules`, `asset_audit_log`.
- Transport tables only where the retained V3 transport integration actually uses them; validate this dependency separately before excluding any.

### Legacy schedule family

For an existing database, preserve the schedule tables and their rows until a separately reviewed archival/retention decision exists. The new runtime must stop querying them. For a clean V3 database, do not create them once startup, imports, backup/restore, calendar sync, offline storage and tests have been proven independent of them.

Do not simply remove tables from `schema.sql` or the PostgreSQL fixture while the runtime still expects them. That would create a startup failure, not a completed retirement.

## Safe implementation sequence

1. **Inventory references:** search route dispatch, startup, imports, background jobs, calendar/iCloud sync, backup/restore, offline cache, widget, Studio, installer and tests. Classify each hit as active V3, compatibility-only, or retired.
2. **Retire entry points:** keep schedule endpoints returning 404; remove schedule UI/menu/default prompts and prevent legacy Admin routes from loading. Remove imports only when no active route calls them.
3. **Decouple startup:** split V3 schema validation from legacy schedule validation. Remove shift seeding/triggers/rebuild logic from the fresh-install path, while leaving existing SQLite legacy rows untouched.
4. **Build a fresh V3 PostgreSQL schema:** derive it from active V3 table/column requirements and reviewed PostgreSQL migrations, not by copying the old snapshot. Keep auth and owner schemas separate; create a per-user schema strategy only after its isolation model is tested.
5. **Dual-fixture testing:** one clean V3 database with no schedule tables must start and pass organiser, personal-item, Studio, auth, calendar and asset tests. A separate legacy-upgrade fixture must prove schedule rows remain unchanged and no destructive SQL runs.
6. **Preflight and release:** run the read-only `HOSTED_SCHEMA_PREFLIGHT.sql` only against a provisioned test schema. It currently checks the compatibility schema, so replace/retarget its expected table list after the fresh V3 schema and startup validator are deliberately changed. Do not interpret this compatibility preflight as final V3 acceptance.
7. **Live rollout:** only after external Neon/Render/R2 credentials are configured, verify login, user isolation, persistence across redeploy, backup/restore, offline sync and mobile PWA update. Keep the existing Render service and domain DNS untouched until all gates pass.

## Acceptance criteria

- Fresh V3 PostgreSQL schema contains no active shift planner tables and app startup succeeds without them.
- Existing legacy databases are not destructively changed; schedule/leave rows survive schema initialization and any upgrade rehearsal.
- Public schedule APIs and old shift menus remain retired.
- No user, Owner, or tester data is mixed across schemas.
- CI tests both a fresh V3 schema and a legacy-data preservation fixture.
- Production is not marked ready based only on a local or CI database fixture.
