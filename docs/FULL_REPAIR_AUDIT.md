# Align V3.0 — Full repair audit

**Audit date:** 4 November 2026  
**Repository:** `wjb006/Align-V3.0`  
**Working branch:** `codex/align-v3-full-repair`  
**Base:** `codex/align-v3-rebuild`  
**Scope:** full end-to-end repair; no live deployment or production database changes.

## Verified architecture

- The canonical application is repository-root `app.py` with root `static/` and `migrations/`. `align_paths.py` resolves source files relative to the root application, and `desktop/align.spec` packages root static assets and migrations.
- `programme/app/` is a divergent older copy. It is not the source used by the current root entry point or desktop PyInstaller spec. Do not blindly copy it over the canonical source.
- Build 156 shift planner and Work rota import are present. Rota approval writes to the existing `shifts` table, not a parallel shift store.
- Existing hosted databases require migration 157 for rota import and migration 158 for guided sections/events. Hosted schema migrations are not automatically applied at startup.
- Management Studio embeds the real app at `/?studioLivePreview=1`. The root Studio page had a stale shared stylesheet reference (`styles.css?v=156-v48`) while the app shell uses `156-v67`.

## Repairs made on this branch

- **Home weather:** Home previously rendered a weather chip only if weather had already been loaded elsewhere; the fetch was started by Today, not Home. Home now starts the existing phone-location → saved-town fallback → weather request flow, shows a loading state, exposes a visible unavailable/retry state on failure, and labels a saved forecast when a refresh fails.
- **Weather regression coverage:** `test_weather_timeout.js` now covers Home-only loading, successful display, provider failure/retry, location timeout, saved-town fallback and late geolocation callbacks.
- **Work Calendar setup:** The Sections renderer had an unconditional early return that bypassed the Work opt-in path; the intended opt-in code was unreachable and referenced an undefined variable. It now routes first-time users through the optional Work database enable/form flow, then shows Manage Work Calendar and Upload my rota once enabled. A focused regression test covers both states.
- **Shift travel selection:** The Travel screen advertised “shift or event” and the setup guide documented `shift:<id>`, but the picker only listed organiser/imported-calendar events and the resolver rejected shifts. Upcoming shifts now appear in the picker, and `shift:<id>` resolves to the saved workplace and local shift start time.
- **Travel geocoding:** OTP requires coordinate-backed place selections; it cannot geocode free-text addresses. The UI previously suggested that typed addresses could be left unresolved and sent them to OTP. It now requires selected coordinate-backed places for OTP, while HERE can resolve typed addresses after consent. Saved text-only addresses are not offered as usable OTP coordinates.
- **Travel regression coverage:** `test_transport_build149.py` covers shift discovery, destination/time resolution and the no-shift-schema response. `test_travel_autofill.js` covers OTP coordinate requirements and HERE address resolution.
- **No-console launcher:** `Start Align (No CMD).vbs` now enables Transport only when an OTP URL is already configured or the local listener on port 8080 is reachable. It does not start OTP itself; the Merseyside launcher remains responsible for starting the service.
- **Launcher documentation:** `TRANSPORT_SETUP.md` documents the no-console detection behaviour.
- **Database selection:** desktop content scoring now counts all user-data tables, including shifts/rota, rather than overlooking records outside the original organiser tables. A regression case proves a shift-only legacy database is not overlooked. Database adoption uses SQLite's backup API and retains the source database.
- **Management Studio asset:** the root Studio page now uses the current shared stylesheet cache revision.

## Remaining gaps and release blockers

1. **Automatic shift-travel enrichment:** manual Transport-tab planning for shifts is restored. Automatically enriching a newly approved shift with a route/reminder is not yet implemented. It needs a separate idempotent design that does not create duplicate organiser events or make rota undo mistake generated travel notes for user edits.
2. **Rota image recognition:** JPEG/PNG/HEIC and scanned PDFs are accepted for safe type checking but are not OCR-read. No OCR provider is configured or approved. The UI discloses this; do not imply photo-based extraction works.
3. **Hosted migration state:** migrations 157 and 158 must be verified on disposable SQLite and PostgreSQL fixtures, then the actual hosted schema must be inspected before any production migration. No production migration is performed by this branch.
4. **OTP runtime:** the no-console launcher detects an existing OTP listener but does not start it. Use the Merseyside launcher when the local service needs to be started. An explicit `ALIGN_OTP_URL` is inherited; a configured URL alone does not prove the provider is reachable.
5. **Management Studio:** live iframe sizing/reload, Builder/Design/Owner tabs, form/database builder, Flowchart Builder and phone-width behaviour still need a full browser audit.
6. **CI acceptance:** the latest observed browser, navigation, hosted-persistence and Windows-package workflows all failed before executing any job steps, with no runner assigned. A retry of failed jobs produced the same result. The job-log endpoint had no log blob. This is a GitHub Actions job-start failure, not evidence that an application test failed; no current test pass is claimed.
7. **Runtime acceptance:** no local Windows environment, user database, browser session or live provider credentials are available through this repository inspection. No local or live end-to-end test is claimed.
8. **Legacy account compatibility:** `/api/beta/*`, `beta_users.sqlite3`, `beta_*` modules and `ALIGN_BETA_MODE` remain compatibility plumbing for hosted authentication, Owner access, iCloud credentials and remote access. Do not remove these names without a data/API migration and rollback plan.
9. **Source-copy divergence:** root and `programme/app/` Management Studio pages differ in markup and assets. The root is canonical for current builds. Any packaged/legacy copy must be reconciled deliberately, not overwritten wholesale.

## Repair order

- [x] Restore Home dashboard weather loading and visible failure/retry behaviour.
- [x] Repair the Sections-page Work Calendar entry point so first-time setup enables the optional Work database/form before opening Work settings; add a regression test.
- [x] Add Home weather regression coverage.
- [x] Restore manual Transport-tab journey selection and route resolution for first-class shifts.
- [x] Correct OTP/HERE place-resolution behaviour and add focused UI regression coverage.
- [x] Enable Transport safely in the no-console launcher only when an OTP URL is configured or the local listener is reachable.
- [x] Count all user-data tables when choosing between desktop database candidates.
- [x] Refresh the stale shared stylesheet cache reference in the canonical Management Studio page.
- [ ] Execute the full Python suite, JavaScript/navigation checks, Playwright desktop/mobile browser matrix, desktop package build and PowerShell/VBScript parser checks. CI job-start failures currently block automated execution.
- [ ] Exercise Work opt-in → rota upload → review/correction → approval → planner/Today visibility → undo against an isolated database.
- [ ] Verify migrations 157/158 on disposable SQLite and PostgreSQL fixtures.
- [ ] Implement and test automatic shift-travel enrichment after approval.
- [ ] Audit Management Studio live preview, Builder/Design/Owner controls, form/database builder and Flowchart Builder at desktop and phone widths.
- [ ] Verify launcher modes and database selection with the moved local database, preserving all originals and hosted account authentication.
- [ ] Reconcile release packaging and deployment configuration; deploy only after CI, backup, migration and live health gates pass.

## Safety constraints

- Preserve all existing local and hosted data.
- Do not apply migrations to production or change Render, Neon, DNS, secrets, OTP services or object storage as part of this audit.
- Do not remove compatibility account/authentication code until a reviewed migration and rollback plan exists.
- Do not claim a feature is working based only on source presence or historical test results.
