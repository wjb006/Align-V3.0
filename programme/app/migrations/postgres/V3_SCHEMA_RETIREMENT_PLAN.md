# Align V3.0 fresh-schema and legacy schedule retirement plan

**Status:** fresh-schema implementation added; CI acceptance and live rollout remain pending.  
**Safety rule:** do not drop, truncate, rename, or overwrite existing schedule tables/data as part of V3.0 launch preparation.

## Why this is a release gate

The user-facing V3 flow and fresh PostgreSQL/SQLite schemas are now shift-free. Hosted startup validates only retained V3 tables, and new local databases use the clean SQLite schema. Legacy compatibility code and the original schema snapshots remain for preservation of existing installations; they are not used as fresh V3 provisioning sources. CI acceptance is currently blocked because GitHub Actions jobs terminate before any steps start and expose no logs.

Verified current dependencies:
- `app.py::initialise_database_at` validates the active V3 model in PostgreSQL mode. Fresh SQLite files use `schema_v3.sqlite.sql`; files containing legacy schedule tables remain on a compatibility path that preserves their rows and does not reseed or rewrite schedule data.
- `postgres_support.validate_v3_storage()` validates retained V3 tables and columns only. The obsolete `validate_planner()` entrypoint has been removed.
- Active Home, personal availability, Travel lookup/refresh, iCloud sync, phone push, calendar export, and the Scriptable widget no longer query the legacy schedule tables. Offline legacy shift batches already stored in IndexedDB are retained locally but are not replayed to V3.
- Public shift/leave/work-setup APIs are rejected before opening storage. The legacy Admin URL redirects to Management Studio. Unused `static/week-planner.js` and `static/work-setup.js` files have been removed.
- Existing legacy schedule/leave records are still covered by a preservation regression; no table drops, truncations, or live database changes were performed.
- The legacy table family remains in `schema.sql` and `migrations/postgres/bootstrap.sql` solely for compatibility/recovery paths. Fresh V3 schemas deliberately omit it.
## Target table families

### Keep in a fresh V3 schema

- Account/authentication: `beta_users`, `beta_sessions`, invites, password resets, idempotency, audit/rate events, email settings and encrypted integration credentials.
- Personal organiser: `settings`, `personal_items`, `menu_branches`, `parent_menu_branches`, `organiser_sections`, `organiser_events`, `calendar_links`, `calendar_sources`, `calendar_events`, `calendar_sync_state`, `icloud_config`, `icloud_items`.
- Configurable Studio/database forms: `builder_config`, `builder_records`, `section_defs`, `section_fields`.
- Asset Studio: `assets`, `asset_categories`, `asset_variants`, `asset_usage_rules`, `asset_audit_log`.
- Transport tables: `transport_preferences` and `transport_journey_cache` are retained because the V3 Travel integration actively uses them.

### Legacy schedule family

For an existing database, preserve the schedule tables and their rows until a separately reviewed archival/retention decision exists. The new runtime must stop querying them. For a clean V3 database, do not create them once startup, imports, backup/restore, calendar sync, offline storage and tests have been proven independent of them.

Do not simply remove tables from `schema.sql` or the PostgreSQL fixture while the runtime still expects them. That would create a startup failure, not a completed retirement.

## Safe implementation sequence

1. **Inventory references:** public APIs, Home/availability, Travel, iCloud, phone push, backup validation, offline outbox, and Scriptable widget have been audited for active shift-table queries. Remaining shift-named helper functions in `app.py` and legacy schemas are compatibility-only and are the next cleanup target.
2. **Retire entry points:** schedule endpoints return 404 before database access; the dead location/shift-type/template Admin handlers and their validation helpers have been removed. The active app no longer imports `work_setup.py`; shared colour validation now lives in `colour_utils.py`. Remaining legacy planner functions and scripts are compatibility-only and are being reviewed separately.
3. **Decouple startup:** hosted PostgreSQL startup is validation-only and performs no schema DDL. Calendar location and persistent Travel tables are provisioned by explicit migration 153. Fresh local SQLite databases now use `schema_v3.sqlite.sql` without schedule tables or legacy seeding; only existing SQLite databases containing legacy schedule tables use the preservation compatibility path.
4. **Build a fresh V3 PostgreSQL schema:** added `migrations/postgres/fresh_v3_schema.sql` from the retained V3 table families, with separate auth/owner schemas and no schedule-planner tables. New tester schemas now use this clean DDL; the legacy `bootstrap.sql` is retained only for compatibility tests.
5. **Dual-fixture testing:** added isolated PostgreSQL startup/personal-item tests against a schema with no schedule tables, a tester-schema provisioning test, a fresh local SQLite schema test, and Travel lookup tests without schedule tables. The compatibility fixture/test continues to prove legacy-row preservation. GitHub Actions must complete these tests before this gate is marked accepted.
6. **Preflight and release:** `HOSTED_SCHEMA_PREFLIGHT.sql` targets the fresh V3 schema and checks migration 153 plus absence of retired tables. `HOSTED_SCHEMA_PREFLIGHT_COMPATIBILITY.sql` retains legacy table/data-count checks for upgrade rehearsals. GitHub Actions currently terminates before job steps, so neither the latest code nor the live Neon environment is accepted yet.
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
- Fresh local SQLite startup now uses `schema_v3.sqlite.sql`, with only active organiser, Studio, asset, calendar, iCloud and Travel tables. Existing files containing any legacy schedule table remain on the compatibility initializer, and a regression test verifies those rows survive reinitialisation.
- The Home bootstrap, availability calculation, Travel refresh, calendar feed, iCloud sync and legacy Admin entrypoint no longer query or expose shift-planner tables; the old Admin URL redirects to Management Studio.
- Added explicit PostgreSQL migration 153 for calendar-event destinations and persistent Travel storage. Existing data is preserved; no live database was altered.
- Added the shift-free `fresh_v3_schema.sql`, switched tester-schema provisioning to it, and updated the CI preflight to install and check that schema.
- Removed the unreachable legacy schedule Admin handlers while keeping public legacy routes as explicit 404s.
- Acceptance is still pending: latest GitHub Actions runs on commits after `153f4ef2` failed before starting any steps (zero steps and no job logs). Re-run the full CI matrix once GitHub Actions accepts jobs; do not treat these infrastructure-level failures as a code pass or a test failure.


### Additional legacy isolation

- On 2026-10-12, the active app's remaining `work_setup.py` imports were replaced by a small shared colour validator, and the obsolete hosted `validate_planner()` entrypoint was removed. The Travel event selector now reads only organiser/imported-calendar tables and rejects legacy shift targets. The Windows installer verifies retained V3 tables rather than requiring schedule tables. Existing backups still retain any legacy data; restore does not drop or rewrite those rows.


- Further 12 October cleanup: phone push now reads only personal reminders; the offline store no longer creates/replays shift batches but preserves previously queued entries; the Scriptable widget and guide now use the V3 event feed; retired week-planner and fixed work-setup client files were removed; the Windows installer verifies retained V3 tables.
