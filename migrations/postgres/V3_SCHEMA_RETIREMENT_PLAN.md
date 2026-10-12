# Align V3.0 fresh-schema and legacy schedule retirement plan

**Status:** fresh-schema implementation added; CI acceptance and live rollout remain pending.  
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

1. **Inventory references:** public schedule APIs are guarded before database access; Travel no longer lists shift records; remaining SQLite/iCloud/backup compatibility references still require the full audit below. Keep classifying hits as active V3, compatibility-only, or retired.
2. **Retire entry points:** schedule endpoints return 404 before database access; the dead location/shift-type/template Admin handlers and their validation helpers have been removed. Continue the broader reference audit before deleting remaining compatibility code.
3. **Decouple startup:** hosted PostgreSQL startup is validation-only and performs no schema DDL. Calendar location and persistent Travel tables are provisioned by explicit migration 153. The existing SQLite compatibility initializer still contains legacy migrations/seeding and must be retired separately without deleting old rows.
4. **Build a fresh V3 PostgreSQL schema:** added `migrations/postgres/fresh_v3_schema.sql` from the retained V3 table families, with separate auth/owner schemas and no schedule-planner tables. New tester schemas now use this clean DDL; the legacy `bootstrap.sql` is retained only for compatibility tests.
5. **Dual-fixture testing:** added an isolated PostgreSQL test for hosted startup and personal-item writes against a schema with no schedule tables, plus a tester-schema provisioning test. The separate compatibility fixture continues to exercise legacy-row preservation. GitHub Actions must complete these tests before this gate is marked accepted.
6. **Preflight and release:** `HOSTED_SCHEMA_PREFLIGHT.sql` now targets the fresh V3 schema and checks migration 153 plus absence of retired tables. `HOSTED_SCHEMA_PREFLIGHT_COMPATIBILITY.sql` retains the legacy table/data-count checks for upgrade rehearsals. Do not interpret either as live Neon acceptance.
7. **Live rollout:** only after external Neon/Render/R2 credentials are configured, verify login, user isolation, persistence across redeploy, backup/restore, offline sync and mobile PWA update. Keep the existing Render service and domain DNS untouched until all gates pass.

## Acceptance criteria

- Fresh V3 PostgreSQL schema contains no active shift planner tables and app startup succeeds without them.
- Existing legacy databases are not destructively changed; schedule/leave rows survive schema initialization and any upgrade rehearsal.
- Public schedule APIs and old shift menus remain retired.
- No user, Owner, or tester data is mixed across schemas.
- CI tests both a fresh V3 schema and a legacy-data preservation fixture.
- Production is not marked ready based only on a local or CI database fixture.


## 2026-10-12 implementation update

- Hosted startup no longer calls schema-mutating calendar or Travel preparation functions; readiness validates the required retained tables and columns.
- Added explicit PostgreSQL migration 153 for calendar-event destinations and persistent Travel storage. Existing data is preserved; no live database was altered.
- Added the shift-free `fresh_v3_schema.sql`, switched tester-schema provisioning to it, and updated the CI preflight to install and check that schema.
- Removed the unreachable legacy schedule Admin handlers while keeping public legacy routes as explicit 404s.
- Acceptance is still pending: latest GitHub Actions runs on commits after `153f4ef2` failed before starting any steps (zero steps and no job logs). Re-run the full CI matrix once GitHub Actions accepts jobs; do not treat these infrastructure-level failures as a code pass or a test failure.
