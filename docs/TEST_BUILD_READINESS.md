# Align V3.0 — Test Build 157 Readiness

**Test branch:** `test/align-v3-completion-20261106`  
**Base:** `codex/align-v3-rebuild` (includes the local desktop sign-in work from PR #97)  
**Build:** 157 / V3.0  
**Purpose:** isolated Windows and browser testing. This branch is not production and is not authorised for automatic deployment.

## Included in this test build

- Local desktop Owner account and persistent sign-in, with sign-out and authentication storage separate from planner records.
- Work Settings: contracted hours, pay rate, leave allowance/year, minimum rest, multiple workplaces and addresses, shift areas, start-time/duration/break options, and weekday patterns.
- Work Settings persistence through the existing `/api/work-setup` route and existing location, shift-type and shift-template tables.
- Rota import for CSV, XLSX and text PDFs, plus local Tesseract OCR for JPG/PNG photographs and scanned PDF pages. HEIC is enabled only when the bundled decoder is available.
- OCR is local. No rota image, PDF, extracted text or crop is sent to a third-party OCR/AI endpoint.
- Review/correction, confidence indicators, explicit approval, duplicate/overlap checks, import provenance and guarded undo into the existing shift planner.
- Temporary source-file cleanup and upload limits remain in place.
- Windows package workflow installs a pinned Tesseract 5.5.3 runtime and bundles the executable, DLLs and language data with the test package.
- Build 157 asset/cache version bump to prevent the browser reusing older Work and rota scripts.

## Test coverage added to the Windows workflow

- Desktop sign-in unit and HTTP regressions.
- Work Settings save/reopen tests covering multiple workplaces, areas, time patterns, weekday assignments, pay/leave settings, validation and preservation of existing scheduled shifts.
- Rota import tests for file safety, parsing, review, approval, undo, and capability reporting.
- Mocked photo and scanned-PDF OCR integration tests.
- Real Tesseract smoke test against a generated rota photograph and an image-only PDF. This must run on the Windows build agent with the bundled engine installed.
- JavaScript syntax checks for Work Settings, rota import and desktop sign-in.
- Existing browser matrix and Windows package workflows run from the test pull request.

A test is not considered passed merely because it was added. The GitHub Actions run must complete and report green before this build is called verified.

## Existing architecture and data protection

- Work Settings use the existing `work_setup.py` service and planner tables; no parallel Work shift database is introduced.
- Approved rota rows use the existing `shifts` table and planner validation path.
- The desktop sign-in store remains separate from `align.sqlite3`.
- Local data remains under the user's Align data directory. This test branch does not copy, migrate, reset or delete an existing local database.
- The existing migration 157 rota-import schema and migration 158 section-guide schema are retained. This branch does not apply migrations to Neon or any production database.
- The hosted Asset Studio still requires its separately configured S3-compatible persistent bucket and credentials. This test branch does not create a bucket or change Render secrets.
- Existing beta-to-V3 data transfer remains a separate controlled migration task; no user data has been copied.

## Test steps

1. Wait for the test pull request's GitHub Actions workflows to finish.
2. Download the Windows package artifact from the successful **Align Management Studio Windows package** workflow run.
3. Install and launch the test package using a separate test profile/data directory. Do not point it at the everyday Align database.
4. Open Work Settings; save two workplaces, multiple shift areas, time patterns and weekday assignments; close/reopen Align and confirm they persist.
5. Upload a sanitised sample rota photograph, a scanned PDF, an XLSX and a CSV. Confirm the detected rows, dates, times, locations and areas in Review.
6. Correct at least one row, reject one row, approve selected rows, confirm the approved shifts appear in the planner, and test guarded undo.
7. Sign out, close and reopen Align; verify the sign-in gate and remembered-session behaviour.
8. Confirm the existing planner database and unrelated records are unchanged.

## Release blockers (not silently treated as complete)

- Successful GitHub Actions run and downloadable Windows package.
- Real Windows/WebView2 launch, restart, sign-in and persistence verification.
- OCR accuracy against representative, sanitised rota layouts; handwriting and heavily compressed photographs may still need manual correction.
- Real-world validation of Work Settings and imported shifts on the target Windows machine.
- Dedicated Neon schema/migration rehearsal and hosted account-isolation checks.
- Persistent S3-compatible bucket provisioning and live Studio upload/restore verification.
- Controlled beta-to-V3 data-transfer rehearsal and backup/restore acceptance.
- Separate production release approval. No production deployment, domain/DNS change, Render setting change or live database change is part of this test build.
