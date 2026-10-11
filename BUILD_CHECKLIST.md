# Align V3.0 build checklist
**Live project handoff document**

- **Last updated:** 11 October 2026
- **Workspace:** `C:\Users\wjboy\OneDrive\Documents\ChatGPT\Align V3.0`
- **Original source (read-only):** `C:\Align\Align_App`
- **Working branch:** `codex/align-v3-rebuild`
- **Current commit at last check:** `b280346` — `Complete Outlook and iCloud setup flows`; follow-up email-roster/cache/CI workflow fixes are in progress locally
**Scope:** Align V3.0 implementation from the supplied Codex brief, with the user's explicit Align V3.0 naming taking precedence over any older product name in the brief.
**Domain:** `getalign.co.uk` is owned by the user through IONOS; current DNS still points to existing IONOS hosting. Do not change records until Render provides the verified target.
## How to use this document
- This is the running handoff/checklist. Update the date, evidence, and task boxes whenever implementation or verification changes.
- `[x]` means implemented and checked to the evidence listed. `[~]` means partly done or needs further verification. `[ ]` means outstanding. `[!]` means blocked by an external dependency or user decision.
- Keep code implementation, automated checks, and live deployment/device verification distinct. A local pass does not prove a hosted service or phone installation is current.
- The last known test results are snapshots from this workspace and may become stale as files change. Re-run relevant checks after changes.
- Preserve `C:\Align\Align_App` as read-only. Preserve user data and unrelated working-tree changes.
- GitHub remote is `origin` → private `wjb006/Align-V3.0`; no V3 Render service or dedicated database is provisioned yet.
## Current handoff: resume here
- [~] Main rebuild work continues on `codex/align-v3-rebuild`; event-feed and test-retirement changes are committed and pushed (`347ab82`).
- [x] Current work includes the Studio's phone-preview section-to-database input-matrix flow: create a section or open its editor; new sections start with required Name, optional Date, and review-before-save; the editor describes naming, matrix setup, and form review.
- [x] Latest full Python run: `.venv\Scripts\python.exe -m pytest -q` — **227 passed, 3 skipped, 23 subtests passed** (11 October 2026); latest Outlook and iCloud changes included.
- [x] Latest desktop Playwright run: `node browser-tests/align.spec.js` — passed, covering section records, calendar event list/month views, Studio draft/publish, and phone preview. Shift totals and annual-leave UI expectations were removed from the retained calendar check.
- [x] Latest focused verification: `node test_core_navigation.js`, `node test_display_dates.js`, `node test_ui_polish.js`, `python verify_align_build156.py`, desktop Chromium regression, and `git diff --check` passed (11 October 2026).
- [~] iCloud calendar selection now lists all calendars in the connected account, lets users select existing calendars or create new ones, creates a matching quick-add Section, and offers an event/reminder calendar dropdown with a “Create New Calendar” option. Reminder entries also create/remove their linked Section calendar event. Focused regressions and desktop browser checks pass; verify with a real Apple account, connected calendar sync, and hosted user isolation before marking complete.
- [~] Pixel 7 Chromium and iPhone 13 WebKit passed in an earlier browser matrix, before the newest database-matrix handoff changes. Re-run those profiles after the next meaningful UI changes.
- [~] Shift removal remains the largest local brief requirement. The public V3 user flow and selected shift APIs are retired; legacy modules, local Admin UI and schema still contain shift functionality. Legacy shift data remains stored. Align's subscribed calendar and iCloud sync now use Section events only.
- [~] Work is being replaced by an optional Studio database. Owner Studio field associations and per-user opt-in are implemented; focused server/navigation checks and desktop browser flow pass. Full mobile browser matrix and hosted privacy/isolation verification remain outstanding.
- [x] Removed fixed pay, default-work-calendar, and shift-alert questions from the fallback first-run screen; Settings now uses account-safe profile/calendar/appearance sections without requiring the legacy admin master payload.
- [x] Re-read the supplied brief and scoped the shift-removal dependency map before edits. It spans `app.py`, `planner_api.py`, `admin_api.py`, `align_settings.py`, `work_setup.py`, `transport_places.py`, `transport_service.py`, `travel_refresh.py`, `icloud_sync.py`, `static/app.js`, `static/week-planner.js`, `static/work-setup.js`, schema/migrations, service-worker routes, and shift/work tests. Shift data tables are still present and must be handled with a preservation-safe migration.
- [x] Keep this file current as each checklist item changes.
## 1. Project identity, source and Git hygiene
- [x] Establish a separate Align V3.0 workspace; leave `C:\Align\Align_App` unmodified.
- [x] Use branch `codex/align-v3-rebuild` for this work.
- [x] Rename user-facing product identity and local Owner/remote-access launchers to Align V3.0 / Align names; update known launcher references.
- [~] Internal legacy module/file names still include `beta_*` and internal `BUILD_VERSION=156`; review remaining names as shift and admin functionality are retired.
- [x] Created the new private repository `wjb006/Align-V3.0`; existing private `wjb006/Align-app` remains untouched.
- [x] Added the new repository as `origin`; reviewed ignore rules (local `.env` and SQLite databases excluded); latest pushed development commit is `c64fb25` on `codex/align-v3-rebuild`.
- [~] Keep the pushed branch as development work only until legacy test expectations are retired/updated, browser checks pass on the final shift-free flow, and hosted persistence is verified.
- [x] Domain ownership confirmed by user: `getalign.co.uk` is managed through IONOS; RDAP reports active registration to 9 September 2027. DNS currently resolves to IONOS hosting (`217.160.0.25` and `2001:8d8:100f:f000::200`).
- [x] Commit and push the profile/Settings and event-only calendar regression updates after focused verification (`c64fb25`, `e01478c`, `f53c182`).
## 7. Hosted service, database, and custom domain
- [x] Render workspace `Align-App` (`tea-dagsdf6k1f9s73dof7i0`) inspected read-only; no additional workspace is needed.
- [~] Existing free Render service `align-beta-preview` uses `wjb006/Align-app` main and remains untouched. No Render Postgres instance exists in this workspace.
- [x] Rechecked Render on 11 October: workspace `Align-App` still has only `align-beta-preview` on `wjb006/Align-app`; no Render Postgres exists. Existing service and IONOS DNS remain untouched.
- [!] Neon connector still requires reauthentication (confirmed 11 October 2026); browser sign-in is open for the user to authenticate, then the connector can inspect/create the dedicated database and retrieve a connection string.
- [~] `render.yaml` prepared for service `align-v3` with intended public URL `https://getalign.co.uk`; hosted authentication still uses legacy account-mode compatibility, which must be reviewed before public release.
- [ ] Push reviewed V3 source to `wjb006/Align-V3.0` and connect Render to that repository/branch. The latest source is local; do not deploy the previous commit as if it included these changes.
- [ ] Create dedicated Neon Postgres 18 database and configure secrets without reusing existing Align credentials or databases.
- [ ] Provision the Render service only after branch and database are ready; verify health, auth, migrations, and per-user isolation.
- [ ] Add `getalign.co.uk` as the Render custom domain and verify TLS; then update IONOS DNS to Render's exact provided records and verify propagation.
- [ ] Re-run desktop/Pixel/iPhone browser suites before inviting external testers; full Python suite passed locally on 11 October 2026, while PostgreSQL service-dependent cases remain skipped.
## 2. Retire the legacy shift planner — major outstanding work
- [~] Initial code/schema inventory completed. Full repo search shows broad coupling remains; finish the path-by-path inventory during implementation, including scriptable bridge/widget/iCloud and asset event types.
- [ ] Map and preserve any data the user needs to retain; do not drop user data as a side effect of feature removal.
- [x] Remove the end-user shift scheduler surfaces from Home/calendar and replace the subscribed feed with Section events only; legacy schedules are not published.
- [ ] Remove residual shift creation, editing, alert, configuration, admin, and old entry-point code.
- [ ] Remove residual shift APIs and backend services after preserving legacy data and checking dependent travel/iCloud flows.
- [ ] Remove shift tables and migration/bootstrap references safely for fresh installs and existing databases; decide/document a safe migration strategy before destructive database changes.
- [ ] Remove residual shift-specific client files after checking that shared calendar/event features remain intact.
- [~] Removed obsolete shift-only test modules (`test_calendar_sync.py`, `test_work_setup.py`, `test_week_booking.py`, `test_shift_completions.py`, `test_work_settings.py`) after moving retained test setup into `test_support.py`; broader shift scripts, UI and documentation remain.
- [ ] Run the full Python suite, JavaScript unit checks, browser suite, startup/schema checks, and fresh-database migration checks.
- [ ] Verify searches show no active shift product functionality remains (distinguish unrelated identifiers such as JavaScript `shiftKey` or array `.shift()`).
**Current release gate:** not ready for external testers. Residual shift modules/admin/schema remain; no V3.0 database/service is provisioned; Neon requires reauthentication; Microsoft Graph and Apple credentials need real-account setup and verification.
## 3. Database-backed Sections and user input matrices
- [x] Add numbered SQLite/Postgres migrations for `calendar_links`, `section_defs`, and `section_fields`; include them in migration expectations and hosted test fixture.
- [x] Materialize published Builder layouts into database section definitions; keep submitted user data in private per-user `builder_records` storage.
- [x] Add published sections to the user application and route them to private record entry/list UI.
- [x] Validate fields and records server-side; preserve record revision/archive behavior and existing user values.
- [x] Add Studio phone-preview handoff to create a new section/input matrix or edit an existing section.
- [x] Guide the Owner through naming the database, creating/reordering questions, and reviewing the resulting form.
- [x] Default new sections to a required Name, optional Date, and review-before-save.
- [x] Verify current matrix handoff and record-related browser behavior in desktop Chromium.
- [~] Validate the full workflow with final shift-free product navigation after shift retirement.
- [ ] Re-run the full three-device browser matrix after the newest matrix flow and all later changes.
- [ ] Validate published data behavior, rollback/history/restore, and per-user privacy against the hosted Owner portal once provisioned.
- [ ] Confirm PostgreSQL 18 migration, schema, CRUD, and isolation behavior against a real test service.
## 4. Owner Management Studio and onboarding
- [x] Serve the Owner-only Studio at `/studio`; keep Owner and Builder access links out of user-facing menus.
- [x] Provide a unified Owner interface for first-run questions, menus, sections, navigation, appearance, review and publishing.
- [x] Add first-run profile questions and persistence; remove forced redirect into Work Setup after onboarding.
- [x] Add draft/publish flow and published-design history/restore controls in the local Studio implementation.
- [x] Add phone preview click and drag reorder for home areas and bottom navigation; save draft ordering.
- [x] Add Owner-only service status showing configuration presence without exposing secret values; show HERE allowance and iCloud configuration state with privacy notes.
- [x] Test Owner status endpoint is Owner-only and redacted (focused Owner tests passed).
- [~] Validate full history/restore and permission behavior in a real hosted Owner session.
- [ ] Complete direct home-block creation from the phone preview (section/database creation is now direct; custom home-area creation is still outstanding).
- [ ] Review Studio usability/accessibility on desktop and phone after final scope is complete.
## 5. Kept features and integrations
- [x] Retain Python `ThreadingHTTPServer`, vanilla JavaScript PWA, SQLite/PostgreSQL support, account workflows, calendar/planner capabilities, travel/weather, iCloud sync, and Finance template as applicable to the brief.
- [x] Move iCloud section calendar routing to `calendar_links` while retaining calendar sync protections.
- [x] Add HERE quota status without returning credentials; show connection configuration by environment-variable name/state only.
- [x] Add environment/deployment documentation, `.env.example`, `render.yaml`, and PostgreSQL bootstrap files.
- [~] Confirm the final retained-feature list against the supplied brief after shift retirement; do not remove unrelated calendar/travel/finance behavior by guesswork.
- [ ] Verify live weather, HERE usage reporting, iCloud sync, calendar history and permissions against the dedicated hosted deployment.
## 6. Persistence and migrations
- [x] Restore the legacy `schema.sql` baseline after discovering its removal broke fresh SQLite startup.
- [x] Add SQLite/PostgreSQL numbered migrations for new calendar and section tables.
- [x] Add isolated PostgreSQL bootstrap and hosted schema test fixture.
- [x] Fresh SQLite initialization passed in the prior implementation run.
- [ ] Verify fresh SQLite install after all shift-related schema retirement changes.
- [ ] Run PostgreSQL 18 integration workflow against a real isolated test database.
- [ ] Verify backups, restore, schema upgrades, and data retention against the final dedicated database.
## 7. Browser, CI and release verification
- [x] Rename browser workflow/spec to `.github/workflows/build-browser.yml` and `browser-tests/align.spec.js`.
- [x] Add browser coverage for desktop Chromium, Pixel 7 Chromium, and iPhone 13 WebKit profiles.
- [x] Most recent local desktop browser regression passes; earlier full device matrix passed before the newest matrix work.
- [x] Align app and service-worker asset cache version at `156-v36`; update Studio-specific asset references and verifier.
- [x] `verify_align_build156.py` passes for Align V3.0 and Build 156 cache identity.
- [x] Full Python suite now passes after retiring obsolete shift-only tests: 222 passed, 3 skipped, 23 subtests.
- [~] Removed Owner-only Asset Studio links from end-user More and Settings; removed Owner phrasing from Work and personal appearance guidance. User menus now expose personal Settings and Travel only. Standalone Align Management Studio retains Owner controls. Local Admin and backup/iCloud maintenance dependencies remain separate. Desktop browser, navigation, UI polish, date, cache verifier, JavaScript syntax, and full Python suite pass (222 passed, 3 skipped, 23 subtests).
- [~] Outlook/Graph setup now has a Management Studio wizard, personal/work account selection, persistent encrypted token handling, test-mail control, automatic invitation/recovery codes, and account/password change notices. Microsoft app registration and mailbox authorization still need the account owner's Client ID and consent; live delivery remains unverified until then.
- [x] Invited and active accounts are included in the required account-email list shown in Management Studio; disabled accounts are marked paused. This list covers setup, recovery, and security emails, not marketing.
- [x] Re-ran the full Python suite after shift-test retirement and end-user management-surface changes; 222 passed, 3 skipped, 23 subtests, no failures.
- [x] Align calendar feed publishes timed and all-day Section events with stable UIDs; old shift/leave rows remain stored but are not published.
- [x] `test_event_calendar_feed.py` verifies ICS output and preservation/non-publication of legacy schedule rows.
- [ ] Re-run desktop, Pixel 7, and iPhone 13 browser profiles after final implementation.
- [ ] Run GitHub Actions CI on the dedicated repository and resolve any real failures.
- [ ] Package only from the exact green commit; verify ZIP contents if a source/release package is required by the brief.
## 8. Hosted infrastructure and launch
- [ ] Create a dedicated Neon PostgreSQL 18 database for Align V3.0; do not point bootstrap files at an existing Align database.
- [ ] Create the dedicated Render service and connect it to the new database.
- [ ] Configure fresh secrets/environment variables securely; do not put secrets in this document or source control.
- [ ] Configure domain/TLS and required email/iCloud/HERE/weather integrations according to the brief.
- [ ] Deploy the exact green commit and wait for the service to report live.
- [ ] Verify hosted build/version through the service's authenticated/official status endpoint (not just a pushed commit or static asset).
- [ ] Verify Owner login, tester account flows, section records, data privacy/isolation, calendar sync, and backups on the hosted service.
- [ ] Verify installed PWA/service-worker update and user-visible behavior on the actual phone profiles/devices.
## 9. Documentation and handoff
- [x] Add initial rebuild summary in `REPORT.md`.
- [x] Create this full running checklist as the primary resume/handoff document.
- [x] Merge Build 153/154/156 V2.1/V2.2 release notes into `RELEASE_NOTES_BUILD156.txt`; remove duplicate note files.
- [x] Remove duplicate top-level migration check SQL; the canonical maintained file is `migrations/POST_MIGRATION_CHECKS.sql`.
- [x] Remove one-off `work/` development scripts from the package and ignore that scratch folder.
- [x] Remove two unused PowerShell update aliases; `align.ps1 update` remains the single source update command.
- [x] Remove an unreferenced Wi-Fi PowerShell alias after confirming the main menu and batch entry points cover Wi-Fi startup.
- [x] Remove `OTP_UPDATE.md`, a historical one-off update guide whose `Install-Update.ps1`/Build 150 instructions are no longer in this package; current install/transport docs remain.
- [~] Audit `.py`, `.ps1`, `.md`, `.bat`, `.sql`, and `.json` assets for safe grouping. Keep runtime modules, distinct entry points, migration history, schemas, and fixture data that active code needs.
- [~] Keep runtime Python modules and SQLite/Postgres migrations separate: imports, schema dialects, and applied migration IDs are live compatibility contracts. Runtime JSON (manifest/provider/stops) and release source package metadata remain separate for the same reason.
- [~] Consolidated the startup flow into `Start Align.bat` (local, Wi-Fi, remote access, transport, Merseyside). The existing Wi-Fi, remote, and transport batch shortcuts delegate to it; distinct OTP/Merseyside setup behavior remains separate.
- [x] Consolidated optional iCloud, account/remote-access, and iPhone HTTPS dependency/setup choices in `Install Align Add-ons.bat` / `Install-Align-AddOns.ps1`; renamed the grouped account dependency file to `requirements-accounts.txt`.
- [x] Combined Java and Docker OTP shutdown in `Stop Align OTP.bat`; removed duplicate Merseyside stop script and obsolete duplicate installers.
- [~] One user-facing Align app identity is in place. Beta-branded launchers and labels are retired; legacy account-mode routes, database tables, and Python module names remain internal for compatibility and need later migration planning before any data/API renames.
- [~] Backup/recovery and release/deploy tools remain separate where they have distinct safety or operational roles; continue only where duplicate behavior is evidenced.
- [x] Updated install guide and conservative uninstaller for the grouped launcher/add-ons entrypoints. Default uninstall continues to preserve the database.
- [x] Keep checklist boxes, last-updated date, latest commit, test evidence, and blockers synchronized after every substantive change.
- [ ] Update `README.md`, install/deployment docs, and release notes once the final shift-free scope and hosting setup are complete.
- [ ] Record final deployment URL/build, repository URL, database/service identifiers (never secret values), tests, known limitations, and rollback procedure here.
## Latest verification log
| Date (Europe/London) | Check | Result |
|---|---|---|
| 2026-10-11 | Full Python suite, `.venv\Scripts\python.exe -m pytest -q` | 227 passed, 3 skipped, 23 subtests passed in 136.51s |
| 2026-10-11 | Desktop Playwright browser regression, `node browser-tests/align.spec.js` | Passed; includes current section matrix create handoff |
| 2026-10-11 | Focused Owner tests | 10 passed |
| 2026-10-11 | `py verify_align_build156.py` | Passed |
| 2026-10-11 | `git diff --check` | No whitespace errors; Git reported CRLF-to-LF normalization warnings |
| 2026-10-11 | PowerShell parser on add-ons, remote access, uninstaller, and cleanup scripts | Passed |
| 2026-10-11 | Aligned cache references and assertions | Updated app, index, service worker, verifier, and focused UI checks to `156-v34`; not yet rerun |
| 2026-10-11 | Created and pushed separate private V3 repository | `wjb006/Align-V3.0`, branch `codex/align-v3-rebuild`; existing `wjb006/Align-app` untouched; local SQLite and `.env` excluded |
| 2026-10-11 | Updated first-run and Settings flow | Removed fixed Work/pay/shift-alert prompts; account-safe Settings; optional Work stays in Sections |
| 2026-10-11 | Current local verification | 20 focused Python tests, core navigation/Work, dates, UI polish, Build 156 cache verifier, diff check, and desktop Playwright passed; full suite not rerun |
| 2026-10-11 | Current full Python suite | 70 failed, 237 passed, 3 skipped, 16 subtests passed; remaining failures all trace to retired shift/work-schedule/iCloud behavior and duplicate collection of imported test base classes |
| 2026-10-11 | Retired schedule-only tests and centralized isolated server fixture | Removed five obsolete shift test modules; retained backup/journey coverage now uses test_support.py; full suite 222 passed, 3 skipped, 23 subtests |
| 2026-10-11 | Event calendar feed | New event-only feed regression passed; desktop Chromium flow passed after feed change; `py_compile` and `git diff --check` passed |
| 2026-10-11 | Hosting refresh | Render connector works; only old `align-beta-preview` exists and no Render Postgres; Neon connector requires reauthentication |
| 2026-10-11 | Script grouping and stale-reference audit | Launch/add-ons grouping implemented; final runtime/browser verification pending |
| 2026-10-11 | File cleanup inventory | Release note duplicates consolidated; duplicate migration check removed; one-off scripts removed; targeted checks pending |
| 2026-10-11 | File cleanup inventory | Removed stale Build 150 one-off update note and unused PowerShell aliases; current launcher references rechecked |
| 2026-10-11 | Optional Work flow | 17 focused Python tests; core navigation, date, UI polish and asset consistency checks passed |
| 2026-10-11 | PowerShell parser | Installer interpolation fixed; installer, uninstaller, cleanup, live-folder, add-ons and remote-access scripts parse successfully |
## Change log
- **2026-10-11:** Created this resumable full-build checklist. Recorded current local implementation, evidence, and remaining work. Added the current database input-matrix flow to the completed items.
- **2026-10-11:** Began replacing fixed shift setup with optional Work records. Added per-user Work opt-in gating and Studio associations for location, area, date, and start/end fields. Started file consolidation by grouping release notes, removing duplicate migration checks, and removing scratch scripts; verify and continue the extension inventory.
- **2026-10-11:** Continued build by reopening the supplied brief and mapping shift planner references to core API/UI, calendar/iCloud, transport, schema, service-worker and test dependencies. No shift code or tables were removed yet; next work must preserve existing database data while disabling/removing active features.
- **2026-10-11:** Audited build/update grouping. Progress and acceptance status are grouped here and in `REPORT.md`; the Playwright matrix is grouped, but operational scripts remain separate and need a duplicate/purpose audit before consolidation.
- **2026-10-11:** Grouped Align startup modes and optional integrations, merged OTP shutdown handling, renamed the account dependency bundle, and updated installer documentation. Beta remains only in legacy account/API/storage compatibility internals; the user-facing app is Align. Bumped coordinated cache revision to `156-v34`; focused verification is pending.
- **2026-10-11:** Focused follow-up passed: core navigation, display-date, UI polish, Scriptable bridge, phone push, Build 156 asset verifier, and 16 Python UI/route/Owner tests. PowerShell parsing passed for the add-ons, remote-access, uninstaller, and cleanup scripts; git diff --check passed (line-ending warnings only).
- **2026-10-11:** Re-ran full Python suite (70 retired schedule failures, 237 passed, 3 skipped, 16 subtests); replaced Align's published shift/leave feed with timed/all-day Section event export. New feed regression and desktop browser pass; old database rows are preserved. Render still has no V3 service/Postgres; Neon connection needs reauthentication.

| 2026-10-11 | Separated user controls from Align Management Studio | Removed Asset Studio entry points from More/Settings, updated user copy, bumped cache revision to 156-v36; full Python 222 passed, 3 skipped, 23 subtests; desktop browser and focused checks passed |
| 2026-10-11 | User-managed iCloud calendars | Added reusable calendar choices, selection checkboxes, quick-add Sections, event/reminder destination dropdowns with “Create New Calendar”, reminder-to-calendar event sync, and cache revision 156-v39; focused tests and desktop browser passed; real Apple account and hosted verification remain outstanding |
| 2026-10-11 | Outlook and user-managed iCloud completion pass | Full Python suite 227 passed, 3 skipped, 23 subtests; desktop Chromium, navigation, display-date, UI, offline asset verifier, and diff check passed; Neon still requires reauthentication; Render has no V3 service and only the old Align-App service |
| 2026-10-11 | GitHub publish readiness | Private repo and branch exist; local reviewed changes are not pushed; Render only has the unrelated old Align-app service; Neon connection is unauthorized |
| 2026-10-11 | Account email list and cache refresh | Management Studio shows which invited/active accounts receive required account emails; disabled accounts are paused; 156-v40 cache check and desktop Chromium passed |
| 2026-10-11 | GitHub workflow targets | Updated CI triggers to the repository's current default branch; old preview health check is manual only until a V3 service exists |
| 2026-10-11 | Hosted PostgreSQL migration correction | CI found runtime DDL blocked by the hosted adapter; moved calendar fields to additive migration 152 and aligned bootstrap/fixture/validation; hosted rerun pending |

- **2026-10-11:** Added user-managed iCloud calendar selection and creation to existing Calendar settings; selected calendars become reusable Sections, and event/reminder forms offer calendar destinations plus a “Create New Calendar” option. Reminder deletion removes its linked Align calendar event. Bumped coordinated cache revision to `156-v39`; 11 focused Python tests, current two focused calendar regressions, JavaScript/cache checks, and desktop Chromium flow passed. Real Apple and hosted account checks are pending.
- **2026-10-11:** Added the Outlook account-email setup and calendar integration work to the local release candidate; full Python/browser/focused checks pass. Shift planner code still remains, Neon access is unauthenticated, and Render's only service targets the old repository. These are launch blockers; the current local changes have not been pushed or deployed.
- **2026-10-11:** Added the requested automatic account-email subscription roster to the existing Management Studio account list and bumped the coordinated asset cache identity to `156-v40`; required account emails are distinguished from marketing. Updated GitHub Actions to run on the repository's current default branch and disabled the unrelated old-service health schedule.
