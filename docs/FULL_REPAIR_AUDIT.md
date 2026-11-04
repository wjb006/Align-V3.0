# Align V3.0 — Full repair audit

**Audit date:** 4 November 2026  
**Repository:** `wjb006/Align-V3.0`  
**Working branch:** `codex/align-v3-full-repair`  
**Base:** `codex/align-v3-rebuild`  
**Scope:** full end-to-end application repair; no live deployment or production database changes.

## Verified architecture

- The canonical application is the repository-root `app.py` with `static/` and `migrations/`. `align_paths.py` resolves source files relative to the root application, and `desktop/align.spec` packages the root `static/` and `migrations/` directories.
- `programme/app/` contains a divergent older copy. It is not the source used by the current root entry point or desktop PyInstaller spec. Do not blindly copy it over the canonical source.
- The Build 156 shift planner is present in the current branch. The rota importer is also present in the root source: `work_rota_api.py`, `work_rota_import.py`, `work_rota_storage.py`, `rota_file_processor.py`, `rota_parser.py`, and `static/work-rota.js`.
- Rota approval writes to the existing `shifts` table, not a parallel shift store. Existing hosted databases require explicit migration 157 before rota import; migration 158 is required for guided sections/events. The application does not apply hosted schema migrations at startup.
- The current Management Studio embeds the real app at `/?studioLivePreview=1`. Its page had a stale shared stylesheet URL (`styles.css?v=156-v48`) while the main app shell uses `156-v67`. This repair branch updates that shared stylesheet reference to the current cache revision.

## Verified gaps and risks

1. **Rota image recognition:** JPEG/PNG/HEIC and scanned PDFs are accepted for safe type checking but are not OCR-read. No OCR provider is configured or approved. The UI correctly discloses this; do not imply photo-based extraction works.
2. **Rota travel enrichment:** the rota handover explicitly records that approved shifts do not yet trigger a shift-specific travel hook. Existing post-event travel is for organiser/imported-calendar events and must not be assumed to cover shifts.
3. **Hosted migration state:** migration 157 and 158 must be verified/applied separately to each relevant existing hosted schema. No production migration is performed by this repair branch.
4. **Launcher / transport configuration:** the no-console VBS launcher sets the port and standard Align mode but does not set `ALIGN_TRANSPORT_ENABLED` or `ALIGN_OTP_URL`. The dedicated Transport and Merseyside launchers do set these. The transport API explicitly returns disabled when the flag is absent. Confirm the intended local OTP startup path before changing the VBS launcher; blindly enabling transport without a running OTP service would only replace a clear disabled state with provider errors.
5. **CI acceptance:** the README records an older fully verified baseline (commit `594cd085`) and states newer runs were terminating before executing steps. The latest merge commit and the new repair PR currently have no workflow runs or status checks returned by the connected GitHub Actions lookup. No current green CI claim is made.
6. **Runtime acceptance:** no local Windows environment, user database, browser session, or live provider credentials are available through this repository inspection. No local or live end-to-end test is claimed.
7. **Legacy account compatibility:** `/api/beta/*`, `beta_users.sqlite3`, `beta_*` modules and `ALIGN_BETA_MODE` remain active compatibility plumbing for hosted authentication, Owner access, iCloud credentials and remote access. Removing these names without a data/API migration would risk existing accounts.
8. **Source-copy divergence:** root and `programme/app/` Management Studio pages differ in markup and assets. The root is canonical for current builds. Any packaged/legacy copy should be reconciled deliberately, not overwritten wholesale.

## Repair order

- [x] Refresh the stale shared stylesheet cache reference in the canonical Management Studio page.
- [x] Make Home weather show a visible unavailable state and retry action when the provider fails; add a regression case for the failure state.
- [~] Restore Home dashboard weather loading, expose a retry state when the provider fails, and add regression coverage; the CI jobs currently fail before any test steps start, so runtime verification remains blocked.
- [ ] Re-run the full Python suite, JavaScript/navigation checks, Playwright desktop/mobile browser matrix, desktop package build, and PowerShell parser checks on the current source. The latest PR-triggered browser, navigation, hosted-persistence and Windows-package runs all conclude `failure` with zero job steps and no runner assigned; this is a GitHub Actions job-start failure, not evidence that an application test failed.
- [ ] Exercise the complete Work opt-in → rota upload → review/correction → approval → planner/Today visibility → undo flow against an isolated database.
- [ ] Verify migration 157/158 on disposable SQLite and PostgreSQL fixtures; separately inspect the actual hosted schema before any production migration.
- [ ] Add and test a safe shift-travel enrichment contract after approval, with resolved location, idempotency, provider-unavailable handling and no duplicate organiser events.
- [ ] Audit journey provider configuration, address resolution, OTP/HERE selection, cached journeys and leave-time display with focused integration tests.
- [ ] Audit Management Studio live iframe sizing, preview reload, Builder/Design/Owner tabs, form/database builder and Flowchart Builder at desktop and phone widths.
- [x] Improve desktop database selection so content scoring counts all user-data tables (including shifts/rota), not only organiser events/sections and builder records; add a rota-only legacy-database regression case.
- [ ] Verify launcher modes and database selection, including preservation of existing local data and hosted account authentication.
- [ ] Reconcile release packaging and deployment configuration; deploy only after CI, backup, migration and live health gates pass.

## Safety constraints

- Preserve all existing local and hosted data.
- Do not apply migrations to production or change Render, Neon, DNS, secrets, OTP services or object storage as part of this audit.
- Do not remove compatibility account/authentication code until a reviewed migration and rollback plan exists.
- Do not claim a feature is working based only on source presence or historical test results.
