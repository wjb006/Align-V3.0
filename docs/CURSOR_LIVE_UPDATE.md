# Align V3.0 — Live Cursor Handover: Work Rota Import

> **Purpose:** This is the current working handover for Cursor. Read this file and `docs/WORK_ROTA_IMPORT_SPEC.md` before changing code. Keep this document updated as implementation progresses.
>
> **Last verified against GitHub:** 3 November 2026  
> **Repository:** `wjb006/Align-V3.0`  
> **Working branch:** `codex/work-rota-import`  
> **Verified branch HEAD at handover creation:** `ee56761f830d0779efa925200484bc5a8c2ce43b`  
> **Base branch:** `codex/align-v3-rebuild`

## 1. Current status — read this first

<badge>Planning committed</badge> **The rota-import feature is NOT implemented yet.**

Completed:
- Created the feature branch `codex/work-rota-import` from `codex/align-v3-rebuild`.
- Added and reviewed `docs/WORK_ROTA_IMPORT_SPEC.md`.
- Confirmed the restored Build 156 shift planner is present and active. The earlier assumption that it had been retired was incorrect; do not revive a legacy planner or create a parallel one.
- Re-inspected the live branch files and schema layout before preparing this handover.

Not completed:
- No rota upload endpoint or upload UI.
- No import-session or pending-entry database tables.
- No PDF, spreadsheet, image extraction or OCR implementation.
- No review/edit/approval/undo workflow.
- No new automated tests for rota import.
- No production deployment or live database change.

**Do not describe the feature as working until these items have been implemented and tested.** The only feature-specific deliverable currently committed is the implementation specification.

## 2. Product decisions already agreed

- Work dashboard action: **Upload my rota**.
- Accept multiple files per import:
  - Images: JPG/JPEG, PNG, HEIC
  - Documents: PDF
  - Spreadsheets: XLSX and CSV
- User reviews extracted entries and explicitly approves before any shift is created.
- User can correct, reject, approve individually or in bulk, and undo imported shifts safely.
- Privacy-first handling: original files and temporary derivatives are used only for processing, stored outside public/static paths, and deleted after processing or failure. Do not create a permanent rota-document archive.
- Keep only the minimum extracted schedule fields needed for the user's own planner.
- Never silently overwrite existing shifts or calendar events.
- No external OCR/AI provider has been selected or approved. Do not send rota data to an external provider without a separate privacy, retention, data-region and cost review.

## 3. Confirmed architecture — reuse it

### Backend

- `app.py` is the HTTP entry point and owns the authenticated request lifecycle and shared DB connection.
- `planner_api.py` is the active canonical shift-planner API.
  - GET planner data reads shifts, locations, shift types, templates and leave.
  - POST `/api/shifts` accepts batches (up to 100), validates through `_shift_values` and `_check_shift`, inserts into `shifts`, creates alerts via `_create_shift_alerts`, and supports `shift_batches.request_id` idempotency.
  - PUT/DELETE already manage existing shifts.
- `work_setup.py` persists the user's Work configuration.
- `owner_builder.py` contains account scoping / optional Work database rules. Respect the existing account boundary and Work opt-in.
- `personal_planner.py` provides Today/daily planner integration. Verify the current contract and test visibility after approval.
- `post_event_travel.py` and `transport_service.py` contain existing journey/transport logic. Reuse only through the supported existing shift/event travel contract after a shift has been approved and a location resolved.
- `organiser_api.py` manages a separate personal organiser event system. **Do not duplicate shift records into `organiser_events`.** The existing `shifts` table is the source of truth for work shifts.

### Frontend

- `static/app.js` is the main app state/render/navigation shell.
- `static/work-setup.js` implements Work settings and should be consulted for Work navigation and data conventions.
- `static/shift-planner.js` is the existing restored shift planner UI. Preserve it.
- `static/styles.css` contains the existing Align design tokens and component styles.
- `static/service-worker.js` controls offline caching. Ensure new scripts/assets are versioned and cache behaviour is considered if new frontend files are added.

### Database / migrations

- `schema_v3.sqlite.sql` is the fresh local SQLite schema and already includes the restored shift planner.
- `migrations/postgres/fresh_v3_schema.sql` is the fresh hosted PostgreSQL schema and includes Build 156 shift-planner tables.
- `migrations/postgres/156_shift_planner.sql` is the additive migration used to restore the planner on existing hosted databases.
- `migration_runner.py` has explicit local SQLite migration paths, including planner migration handling. Inspect how the new SQLite migration should be registered; do not assume adding a SQL file alone causes it to run.
- Hosted PostgreSQL migrations are explicitly provisioned; the running app does not mutate hosted schemas at startup. Add a corresponding PostgreSQL migration and update the documented provisioning instructions.
- Keep local SQLite, fresh PostgreSQL and existing-hosted PostgreSQL schema paths in parity.

## 4. Required implementation shape

Use the detailed spec in `docs/WORK_ROTA_IMPORT_SPEC.md` as the product and data-contract source. Reconcile proposed filenames with repository conventions before adding modules.

Suggested separation:
- `work_rota_api.py`: authenticated routes, bounded multipart intake, request/response validation.
- `work_rota_storage.py`: account-scoped import session and extracted-entry persistence.
- `rota_file_processor.py`: allowlisted file detection, safe extraction adapters, temporary-file lifecycle.
- `rota_parser.py`: date/time normalization, matching, confidence and ambiguity handling.
- `work_rota_import.py`: transactional approval, idempotency, provenance and safe undo.
- `static/work-rota.js` and optional `static/work-rota.css`: upload and review UI, following existing frontend conventions.

Do not add unnecessary abstractions if a small, testable service fits the existing codebase better.

### Storage model

Create relational tables for:
- `work_rota_imports`: opaque ID, state, counts, safe error category and timestamps.
- `work_rota_entries`: import ID, date/time, shift label, department, resolved location or unresolved location text, entry kind, confidence, review state, revision and created shift link.

Approved shifts MUST be written to the existing `shifts` table. Do not create `work_shifts` or a second planner. Add nullable provenance such as `source_import_entry_id` to `shifts` only if required for unique publication and safe undo; add matching SQLite and PostgreSQL schema changes.

### Proposed API

Register through the existing `app.py` dispatcher and preserve auth, account isolation, Work opt-in and same-origin protections:
- `POST /api/work/rota/imports` — bounded multipart upload.
- `GET /api/work/rota/imports/{id}` — status and review entries.
- `PATCH /api/work/rota/imports/{id}/entries/{entry_id}` — correction with revision checking.
- `POST /api/work/rota/imports/{id}/approve` — selected entry IDs and idempotency key.
- `POST /api/work/rota/imports/{id}/undo` — undo only rows created by this import, with revision/conflict protection.
- `DELETE /api/work/rota/imports/{id}` — cancel/delete pending import data according to state.

Important: `app.py` currently calls `read_json()` for POST requests in its normal path. Multipart handling must be dispatched before JSON parsing, with its own strict Content-Length and stream limits. Do not load unbounded request bodies into memory.

## 5. Processing and privacy requirements

- Allowlist extensions and independently validate MIME/signature; extension alone is not validation.
- Bound total request size, per-file size, file count, PDF pages, spreadsheet rows/columns and image dimensions.
- Reject encrypted/unsupported/malformed documents safely. Do not execute macros or embedded content.
- Random temporary filenames; never use a user filename as a path.
- Temporary storage outside public/static directories with restrictive permissions.
- Clean up source files and all derivatives in `finally` paths; add cleanup for abandoned temporary files after process crashes.
- Do not log rota contents, employee names, addresses, OCR text, raw filenames or file bytes.
- Never return temporary paths or raw OCR provider payloads to the browser.
- Keep raw OCR text and image crops transient; persist only normalized review fields.
- Native spreadsheet and text-PDF extraction can be implemented locally. Image/scanned-PDF OCR needs a real OCR engine; do not fake extraction or label a placeholder as OCR support.
- Before adding dependencies, inspect the existing requirements and hosting environment. The currently inspected `requirements-asset-studio.txt` contains Pillow and boto3, but that is not evidence that a PDF/XLSX/OCR stack is installed. Select and test the actual parser dependencies deliberately.

## 6. Approval, planner and travel rules

- No shifts are written before explicit user approval.
- Reuse planner validation, overlap checking and alert generation. Refactor shared functions into a service only if needed; avoid HTTP self-calls.
- Preserve batch and per-entry idempotency. Retrying approval must not duplicate shifts.
- Validate against existing shifts, annual leave, calendar events and organiser events through existing planner logic.
- Conflicts must be surfaced for user resolution; no silent overwrites.
- Each imported shift must appear in the existing week/month planner and Today view.
- Create the existing shift alerts exactly once.
- Trigger travel enrichment only after successful publication and only when the location is resolved; follow the existing supported contract.
- Undo only the shifts created by this import. Never delete or revert a pre-existing shift or a record subsequently edited by the user without a safe conflict/revision check.

## 7. Recognition and review rules

- High confidence can be preselected, but must remain visible to the user.
- Medium confidence must be clearly flagged.
- Low confidence or missing date/time cannot be approved until corrected.
- Blank cells are not automatically days off.
- Keep day off, annual leave, sickness and unknown distinct.
- Support overnight shifts and the app's established local-time convention.
- Surface ambiguous dates rather than guessing.
- Link a location only on a clear match; otherwise preserve extracted location text and ask the user to resolve it.
- Re-importing the same rota must not duplicate shifts.

## 8. Build sequence — work through it, don't stop at documentation

1. Inspect route dispatch, Work opt-in/account ownership, migration conventions, fresh schemas, frontend navigation and offline asset loading.
2. Add import-session and pending-entry schema changes for SQLite and PostgreSQL, including constraints/indexes and migration registration/provisioning docs.
3. Add storage/service functions and tests for account isolation, state transitions and revisions.
4. Add bounded multipart upload intake and temporary-file cleanup tests.
5. Implement real CSV/XLSX and text-PDF extraction with clear unsupported-file handling. Add a provider-independent OCR interface; only wire a concrete local OCR engine after dependency/hosting review. Do not silently claim images/scanned PDFs work until tested.
6. Implement normalization, Work profile/template/location matching, confidence scoring and review API.
7. Add the Work > Upload my rota UI, progress/error states, review/edit/reject/approve/undo, mobile and keyboard accessibility.
8. Implement transactional approval into `shifts`, alerts, provenance, idempotency, duplicate/conflict handling and safe undo.
9. Verify planner and Today visibility and supported travel enrichment.
10. Run targeted tests, full relevant test suite, SQLite migration tests, hosted PostgreSQL schema/migration tests and browser tests. Inspect the complete diff and update this handover with actual results.

## 9. Minimum test/release gates

- Valid and invalid signatures, unsupported extensions and malformed files.
- Request/file/page/row/column/dimension limits.
- Temporary file deletion on success, failure, cancellation and abandoned-session cleanup.
- CSV/XLSX/PDF parsing; OCR tests for any image/scanned-PDF formats actually claimed as supported.
- UK date formats, ambiguous dates, overnight shifts, daylight-saving boundaries and invalid time ranges.
- Location/template matching and unresolved values.
- Day-off/leave/unknown distinction.
- Duplicate detection, idempotent retry, partial approval and revision conflicts.
- Authenticated account isolation and Work opt-in.
- Exactly one `shifts` row and alert set per approved entry; no duplicate `organiser_events`.
- Undo only removes import-created rows and refuses unsafe reversals.
- Today and week/month planner visibility.
- SQLite and PostgreSQL migration parity; existing hosted schema upgrade instructions.
- No regressions to Work setup, existing shift planner, transport, calendar or Management Studio.

## 10. Hard constraints

- Work on `codex/work-rota-import`; do not commit feature work directly to the base/default branch.
- Do not deploy, run hosted migrations against production, change Render/Neon/IONOS settings, or modify the live site.
- Do not add external OCR/AI transmission without explicit review.
- Do not replace or redesign the existing planner.
- Do not store original rota uploads permanently.
- Do not invent completed functionality or passing test results.
- Prefer complete, integrated implementations over disconnected placeholders. Keep this handover accurate after each meaningful commit.

## 11. Cursor's immediate next action

Start with the migration and route-dispatch inspection, then implement the first vertical slice (schema + secure import session/upload endpoint + tests) on this branch. Keep the upload UI honest about which formats have working extraction. Continue through review and approval rather than stopping after scaffolding. Update this file with commit SHAs, files changed, tests run and outstanding blockers as work progresses.
