# Align V3.0 rebuild report
## Removed or retired
- Replaced the old build-specific browser workflow/spec names with `build-browser.yml` and `align.spec.js`.
- Removed Owner and Builder links from the user-facing menus; the Studio is served through `/studio` and checks Owner authentication.
- Replaced the legacy organiser section index with published database-driven sections.
- Renamed the local Owner setup and remote access launchers to Align names. Updated their cross-file references.
- Grouped local, Wi-Fi, remote-access, transport, and Merseyside startup under `Start Align.bat`; retained thin shortcut delegates for saved entrypoints.
- Grouped optional iCloud, Owner/account, and iPhone HTTPS setup under `Install Align Add-ons.bat` and the shared PowerShell installer. Renamed the account dependency bundle to `requirements-accounts.txt`.
- Combined Docker and portable-Java OTP shutdown in `Stop Align OTP.bat`; removed duplicate optional installers and Merseyside stop entrypoint.
- Restored `schema.sql` after finding that removing its legacy tables made fresh SQLite startup fail. This preserves a working starting point while the remaining legacy shift code is being retired.
## Kept
- Python `ThreadingHTTPServer`, vanilla JavaScript PWA, SQLite and Postgres support, account workflows, travel and weather code, iCloud sync, and the Finance template.
- Existing legacy shift schema and code remain in this checkout. Their removal is not complete.
- The source repository at `C:\Align\Align_App` was not modified. A separate private `wjb006/Align-V3.0` repository is configured as `origin`; development is on `codex/align-v3-rebuild`.
## Changed
- Added numbered SQLite/Postgres migrations for `calendar_links` and `section_defs` / `section_fields`; included them in startup migration expectations and tester schema provisioning.
- Moved iCloud section calendar routing to `calendar_links` while keeping the existing calendar sync protections.
- Materialized published Studio layouts into section definitions and kept user records in private `builder_records` storage. The phone preview supports editing and creating sections with their input matrices, and reordering home areas and navigation buttons. New sections start with a required Name question, optional Date question, and review-before-save. The Owner editor guides setup through naming the section, building the ordered field matrix, and reviewing the entry form.
- Added published sections to the user app and routed them to the private records UI.
- Added `/studio`, an Owner-only status endpoint, integrated Owner settings, and environment-name-only configuration visibility. The Owner panel now includes HERE allowance status and an account-level iCloud configuration indicator without exposing values or calendar details.
- Added first-run profile questions and persistence. Removed the forced redirect into Work Setup after onboarding.
- Rebranded the user-facing app and setup/remote-access launchers as Align V3.0. `BUILD_VERSION=156` remains the internal build/cache identifier.
- Retired the public Beta launchers and user-facing labels. Legacy `/api/beta/*`, `beta_*` database/module names, and `ALIGN_BETA_MODE` remain internal compatibility details; do not rename until a data/API migration can preserve existing accounts.
- Updated the install guide and conservative uninstaller to include the grouped launch and add-ons files while preserving the database by default.
- Bumped coordinated web asset cache revision to `156-v35` after frontend changes.
- Began replacing fixed shift setup with an optional Work database. Studio links custom questions to Work Location, Shift Area, work date, and start/end times; users can opt in and retain private records.
- Updated Management Studio Work matrix to associate custom fields with location, area, work date, and start/end time; Work remains optional and records are private.
- Changed the main Align calendar subscription to export timed and all-day Section events. Legacy shifts and annual-leave rows remain in the database for recovery but are no longer published in the V3 feed.
- Consolidated Build 153/154/156 V2.1/V2.2 release notes into the Build 156 notes file, removed a duplicate SQL verification file, and removed one-off scratch scripts.
- Added `.env.example`, environment/deployment documentation, `render.yaml`, a Postgres bootstrap, and separate hosted-persistence and three-device browser workflows.
## Verification
- Latest full Python run: 222 passed, 3 skipped, 23 subtests passed (11 October 2026). Removed five obsolete shift-only test modules and moved the retained isolated HTTP/SQLite fixture to `test_support.py`.
- New event-feed regression: passed. It covers timed/all-day event export, stable event UID, legacy-row preservation and excluding legacy shifts/leave from the published calendar.
- Latest focused checks: 20 Python tests passed; navigation/Work, date, UI polish, Build 156 asset consistency, and `git diff --check` passed.
- Fixed PowerShell installer interpolation so the embedded Build 156 verification command parses correctly.
- Latest desktop Playwright: section records, calendar event list/month, Studio draft/publish, and phone preview passed. Pixel 7 Chromium and iPhone 13 WebKit need a fresh run after the current UI changes.
- Fresh SQLite initialization succeeded; Python compilation and `git diff --check` succeeded.
- Pushed development snapshot to private `wjb006/Align-V3.0`; no V3 Render service or dedicated Neon database has been provisioned.
- Render reconfirmed to contain only the old `align-beta-preview` service on `wjb006/Align-app`; no Render Postgres exists. Neon tools currently require reauthentication. Existing service and IONOS DNS remain unchanged.
## Outstanding brief requirements
- Remove remaining shift features, tables, APIs, alerts, UI, scripts, and documentation safely. Shift-specific test modules are retired; the legacy Admin planner and schema still need removal.
- Complete and verify the optional Work database flow, including user opt-in and custom field associations.
- Continue source-file grouping only where runtime compatibility and upgrade history are preserved.
- Complete direct creation of home blocks from the phone preview. Section creation/editing now starts directly from the preview, but the actual matrix fields are designed in the guided builder panel. Validate the full history/restore flow against the deployed Owner portal.
- Run the Postgres 18 integration workflow against a real test service.
- Finish the full shift retirement and migrate the remaining legacy Settings/Master UI while preserving old data.
- Provision a dedicated Render service and Neon database with new secrets; existing free `align-beta-preview` remains untouched.
- Add `getalign.co.uk` to the new Render service and only then change IONOS DNS to Render's verified target records.
## Follow-up verification (2026-10-11)
- Focused Node checks passed: core navigation, display dates, UI polish, Scriptable bridge, and phone push worker.
- `verify_align_build156.py` passed with coordinated 156-v35 cache identity.
- Focused Python checks passed: 20 tests across Builder defaults, UI polish, extracted routes, and Owner Builder.
- PowerShell parser accepted the installer, uninstaller, cleanup, live-folder, add-ons, and remote-access scripts. git diff --check passed; Git emitted line-ending normalization warnings.
- Full Python and multi-device browser suites have not been rerun after the latest Work and Settings changes.
