# Align V3 Work Rota Import — Implementation Specification

Status: approved product direction; implementation planning
Target branch: codex/work-rota-import
Base: codex/align-v3-rebuild
Scope: private, user-approved rota import into the existing Align Work and calendar experience.

## 1. Product decisions

- Accept image uploads: JPG/JPEG, PNG, HEIC.
- Accept documents: PDF.
- Accept spreadsheets: XLSX and CSV.
- Support multiple files/pages in one import session.
- Extract shifts into a review queue; never create calendar events before explicit approval.
- Keep original uploads only in temporary processing storage, then delete them after extraction or on failure/expiry.
- Do not retain raw OCR text, image crops, or document derivatives after extraction unless a specific diagnostic is explicitly opted into.
- Preserve confirmed shift data in the user's private Work data.
- Never silently overwrite existing shifts or calendar events.
- Support correction, per-entry approval, bulk approval, duplicate detection and undo.

## 2. Existing V3 architecture mapping

The implementation must extend the current V3 Work setup and restored Build 156 shift-planner infrastructure. The shift-planner tables and planner_api.py handlers are present and active on this branch; do not build a parallel Work shift store or duplicate calendar pipeline.

| Existing module / surface | Integration responsibility |
|---|---|
| app.py | Import and dispatch the rota API handler through the existing authenticated request lifecycle. GET/POST/PUT/DELETE already dispatch to planner_api.py and organiser_api.py with a shared database connection. |
| planner_api.py | Primary integration point. Existing GET planner data reads shifts, locations, shift types, templates and leave; POST /api/shifts validates and inserts shifts, checks overlaps, creates alerts and supports batch idempotency; PUT/DELETE already manage shifts. Extend this service for import provenance and safe bulk approval rather than creating a second shift engine. |
| work_setup.py | Existing Work setup/profile persistence. Use its saved work configuration when matching imported rota details. |
| locations, shift_types, shift_templates, shifts, shift_batches | Existing canonical shift-planner schema, restored by Build 156 and present in the PostgreSQL fresh schema. Reuse these as the source of truth. |
| owner_builder.py | Reuse authenticated-account boundary and optional Work database opt-in rules where applicable. Do not bypass account scoping. |
| organiser_api.py | Existing separate personal/organiser event system. Do not create duplicate organiser_events for shifts already stored in shifts; only use organiser APIs if a future explicit user choice requires a separate calendar event. |
| personal_planner.py | Existing Today/daily planner integration; verify how it surfaces planner_api shift data before wiring import UI. |
| post_event_travel.py and transport_service.py | Reuse existing journey enrichment and transport providers only after approved shifts have a resolved location and the existing shift-travel contract is confirmed. |
| static/app.js | Add the Work > Upload my rota entry and navigation/state integration using existing application conventions. |
| static/builder-runtime.js | Reuse visual conventions and existing Work database interactions where suitable; keep the import-review experience in a dedicated module. |
| static/styles.css | Extend existing Align tokens/components; avoid a parallel visual system. |
| SQLite/PostgreSQL migration conventions | Add equivalent additive schema changes for local and hosted storage; never rely on application-startup schema mutation in hosted production. |

Confirmed route contract: app.py dispatches GET to planner_api.handle_get and POST/PUT/DELETE to planner_api.handle_post/handle_put/handle_delete. The existing POST /api/shifts accepts up to 100 shifts, validates through _shift_values and _check_shift, inserts into shifts, creates alerts and supports shift_batches request_id idempotency. Refactor reusable validation/insert logic or add an importer-specific service that calls the same functions; avoid HTTP self-calls and avoid direct calendar-table writes.

## 3. Proposed modules

New backend modules:

- work_rota_api.py: authenticated routes, upload limits, request validation and response mapping.
- work_rota_storage.py: import-session and extracted-entry persistence, account-scoped queries, status transitions.
- rota_file_processor.py: file type detection, safe parsing, temporary-file lifecycle and extraction adapters.
- rota_ocr_provider.py: provider-independent OCR interface; concrete provider selected only after dependency, hosting, privacy and cost review.
- rota_parser.py: table/layout interpretation, date and time normalization, shift/location matching and confidence scoring.
- work_rota_import.py: approval transaction, idempotency, duplicate checks, calendar publication and undo.

New frontend modules:

- static/work-rota.js: upload, progress, review list, entry editor, approve and undo interactions.
- static/work-rota.css: responsive review/upload styles, reusing existing design tokens.

These names are proposals and should be reconciled with repository naming conventions before creating files.

## 4. Import lifecycle

1. User opens Work > Import rota.
2. Browser uploads one or more files to an authenticated, account-scoped endpoint.
3. Server validates extension, detected MIME type, file signature, file size, page count and upload count. Reject encrypted/unsupported documents and malformed files safely.
4. Files are written to a non-public temporary directory with random names; never use user-supplied paths or filenames as filesystem paths.
5. Processor extracts structured text/layout from each file. OCR is used for images and scanned PDF pages; native text/table extraction is preferred for text PDFs and spreadsheets.
6. Parser normalizes dates, times, shift labels, locations and day-off/leave indicators into candidate entries.
7. Matcher checks the user's configured Work profile, shift templates and saved locations. It must not assume an abbreviation is globally meaningful.
8. Candidate entries are stored as pending review records. Raw source files, OCR text and temporary derivatives are deleted in a finally cleanup path.
9. User edits/approves/rejects individual entries or approves a validated selection.
10. Approval writes confirmed shifts through the existing planner validation and alert-generation logic, with an import-entry provenance link and idempotency. Do not create a duplicate organiser_events row for each shift: shifts are already first-class planner records.
11. Existing travel enrichment is triggered only after event publication and only where a location is resolved.
12. Import summary shows created, skipped, duplicate and unresolved counts. Undo reverses only records/events created by that import, subject to revision checks.

## 5. Proposed data model

Use dedicated relational tables for import sessions and pending extracted entries, but use the existing shifts table for approved shifts. Keep all rows in the authenticated user's existing database/schema.

### work_rota_imports

- id — opaque unique import ID
- status — processing, review, partially_imported, imported, failed, cancelled
- source_file_count
- candidate_count
- created_count
- skipped_count
- error_code — safe machine-readable category, not raw exception text
- created_at, updated_at, completed_at

Do not store original filenames unless necessary; if retained for display, sanitize and treat as metadata.

### work_rota_entries

- id, import_id
- work_date
- start_at, end_at (timezone-aware or consistently stored in the app's established local-time convention)
- shift_label, department
- location_id nullable
- location_text nullable
- entry_kind — shift, day_off, leave, unknown
- confidence numeric, bounded 0..1
- review_status — pending, approved, rejected, imported
- created_shift_id nullable, linking to the existing shifts.id
- revision, timestamps

### Confirmed shift storage

The canonical confirmed shift table already exists: shifts, with work_date, template_id, location_id, shift_type_id, location_name, shift_type_name, colour, start_time, end_time, break_minutes, hours and notes. Reuse it. Add nullable import provenance (for example source_import_entry_id with a unique constraint/index) only if needed to make approval and undo safe. Do not introduce a parallel work_shifts table. Imported shifts should appear through the existing planner_api week/month data and shift UI.

### Indexes and constraints

- Index entries by import and review status.
- Index confirmed shifts by work date and location.
- Unique/idempotency key for each import-entry publication.
- Foreign keys from entries to imports and from published shifts to their originating entry.
- Enforce valid time ranges and valid status values in application validation and, where portable, database constraints.

## 6. API contract (proposed)

All routes must be registered through the existing authenticated app dispatcher and enforce Work opt-in/account ownership.

- POST /api/work/rota/imports — multipart upload; returns import ID and processing status.
- GET /api/work/rota/imports/{id} — status, counts and review entries.
- PATCH /api/work/rota/imports/{id}/entries/{entry_id} — correct one candidate using revision checking.
- POST /api/work/rota/imports/{id}/approve — approve selected entry IDs; explicit idempotency key.
- POST /api/work/rota/imports/{id}/undo — undo only the events/records created by this import.
- DELETE /api/work/rota/imports/{id} — cancel pending import or remove review data according to state.

Do not expose temporary file paths or OCR provider payloads to the browser. Return safe, user-readable errors.

## 7. File safety and privacy

- Allowlist extensions and independently verify file signatures/MIME.
- Set configurable limits for total request bytes, per-file bytes, number of files, PDF pages, spreadsheet rows/columns and image dimensions.
- Reject path traversal, macro-enabled spreadsheets, unsupported archive contents and malformed files.
- Do not execute macros or embedded content.
- Use random temporary filenames and storage outside the public/static directory.
- Restrict temporary directory permissions.
- Delete source files and derived artifacts after processing, including on exceptions and cancellation.
- Add a periodic cleanup for abandoned temporary files/imports after crashes.
- Do not log rota contents, employee names, addresses, OCR text, raw filenames or file bytes.
- Do not send documents to an external OCR/AI provider until its data handling, retention, region, cost and user disclosure have been reviewed.
- Keep only the minimum extracted shift fields required for the user's own schedule.
- Provide an explicit delete action for pending imports and imported shifts.

## 8. Recognition and review rules

- High confidence: preselected for approval, but still visible in review.
- Medium confidence: highlighted and requires user attention.
- Low confidence or missing required time/date: cannot be approved until corrected.
- A blank cell is not automatically a day off.
- Day off, annual leave, sickness and unknown must remain distinct values.
- Overnight shifts must be supported (end time on the following day).
- Locale/date ambiguity must be surfaced, not guessed.
- Timezone and daylight-saving transitions must follow the app's established calendar convention.
- A location is linked only when there is a clear match; otherwise preserve the extracted text and request selection.
- Re-importing the same rota must not duplicate existing shifts. Use a combination of date/time/location/source-entry fingerprint and existing-event overlap checks, with a manual conflict resolution path.

## 9. Calendar and travel integration

- Approval is the only point at which a shift is written to the existing shifts table.
- Reuse planner_api.py validation, overlap checks and alert generation; refactor these into reusable service functions if necessary.
- Preserve the existing shift planner as the single source of truth; do not mirror shifts into organiser_events or create a second calendar source.
- Ensure imported shifts are visible in the existing planner week/month and Today views.
- Trigger existing travel enrichment only through the supported shift-travel integration after the shift is saved and its location is resolved.
- Use a database transaction plus per-entry idempotency/provenance so partial approval can be retried safely and undo removes only shifts created by that import.

## 10. UI requirements

- Work dashboard entry: Upload my rota.
- Drag/drop and mobile photo/file picker.
- Multiple file selection with per-file status.
- Processing state with clear progress stages; do not fake percentage progress when the processor cannot provide it.
- Review screen with date, shift, time, department, location and confidence.
- Original file preview is available only while temporary processing is active; do not promise a retained source preview after deletion. For review after deletion, show extracted values and the specific field needing attention.
- Inline edit, reject, select, bulk approve and undo.
- Accessible controls, keyboard support, responsive layout and plain-language errors.

## 11. Test plan and release gates

Unit tests:
- image/PDF/spreadsheet type detection and invalid signatures
- date/time normalization, overnight shifts and daylight-saving edge cases
- shift abbreviation/location matching
- confidence thresholds and missing fields
- day-off/leave/unknown distinction
- duplicate fingerprints and idempotent approval
- revision conflicts and undo safety

Integration tests:
- authenticated account isolation and Work opt-in enforcement
- upload size/page/row limits
- temporary file deletion on success, failure, cancellation and abandoned-session cleanup
- local SQLite and hosted PostgreSQL migration parity
- approval creates exactly one existing shifts row, one set of shift alerts and one import-provenance link; no duplicate organiser event
- failed calendar publication is recoverable and never falsely reported as complete
- Today/calendar visibility
- travel enrichment uses the existing transport pipeline
- no writes to another user's records

Release gates:
- no deployment until both SQLite and PostgreSQL migrations are tested;
- no production OCR provider until privacy/cost/data-region review is complete;
- no automatic calendar writes before approval;
- no regressions to existing Work setup, calendar, travel or Management Studio flows.

## 12. Implementation order

1. Inspect current route dispatch, Work layout/opt-in, database schema and organiser event creation contract in the target branch.
2. Add schema migration(s) and storage adapter tests.
3. Add authenticated import-session and entry APIs without OCR provider coupling.
4. Build upload and review UI using Align's existing components/styles.
5. Add native PDF/spreadsheet extraction and an OCR provider adapter.
6. Add parser, matching, confidence and correction logic.
7. Add approval into the existing shifts table, alert generation, supported travel trigger and undo.
8. Run full local and hosted-schema tests; review diff before deployment.

## 13. Explicit non-goals for the first release

- Employer/HR system integrations.
- Automatic publishing without user approval.
- Retaining uploaded rota documents as a permanent archive.
- Payroll, timesheets or overtime calculations.
- Sharing or collaborative rota management.
- Learning from user corrections across accounts without an explicit, privacy-reviewed opt-in.
