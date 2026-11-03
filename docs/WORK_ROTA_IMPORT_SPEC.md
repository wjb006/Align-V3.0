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

The implementation must extend the current V3 app rather than restore the retired legacy shift-planner UI/API.

| Existing module / surface | Integration responsibility |
|---|---|
| app.py | Register the new rota API handler alongside the existing API handlers; reuse authentication, request parsing, JSON responses and database connection lifecycle. |
| owner_builder.py | Reuse the authenticated-account boundary and optional Work database opt-in rules. Do not bypass account scoping. |
| builder_records / published Work layout | Reuse for configurable Work profile or supporting metadata where appropriate; do not force time-critical shift rows into arbitrary form fields. |
| organiser_api.py | Reuse the existing organiser/calendar event model and its section/calendar associations when approved shifts are published. |
| personal_planner.py | Ensure approved work events surface in Today and daily planning using existing read paths. |
| post_event_travel.py and transport_service.py | Reuse existing journey enrichment and transport providers after an approved shift has a resolved location. |
| static/app.js | Add the Work > Import rota entry and navigation/state integration using existing application conventions. |
| static/builder-runtime.js | Reuse visual conventions and existing Work database interactions where suitable; keep the import-review experience in a dedicated module. |
| static/styles.css | Extend existing Align tokens/components; avoid a parallel visual system. |
| SQLite/PostgreSQL storage adapters and migration conventions | Add equivalent schema changes for local and hosted storage; never rely on application-startup schema mutation in hosted production. |

Before implementation, verify the exact current route-dispatch order and the organiser event creation contract in the target branch. The importer must call the existing event-creation service/contract rather than writing directly to calendar tables.

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
10. Approval writes confirmed Work shifts and creates/links calendar events through the existing V3 event service in a transaction or a recoverable idempotent workflow.
11. Existing travel enrichment is triggered only after event publication and only where a location is resolved.
12. Import summary shows created, skipped, duplicate and unresolved counts. Undo reverses only records/events created by that import, subject to revision checks.

## 5. Proposed data model

Use dedicated relational tables rather than placing shift rows into generic builder JSON records. Keep all rows in the authenticated user's existing database/schema.

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
- calendar_event_id nullable
- created_work_shift_id nullable if a dedicated Work shift entity is used
- revision, timestamps

### Confirmed shift storage

First inspect the existing current Work/shift schema and the organiser event contract. Reuse an existing canonical Work shift table if it is genuinely active in V3. If none exists, add a dedicated work_shifts table with a stable link to its calendar event. Do not revive legacy endpoints merely because similarly named tables exist.

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

- Approval is the only point at which calendar publication occurs.
- Use the existing organiser event creation/update service and current section/calendar-link conventions.
- Store a durable relationship between the imported Work shift and its calendar event.
- Do not create a second independent calendar source or duplicate event pipeline.
- Preserve user edits to an already-published event; an import must not overwrite them on re-import.
- Trigger existing travel enrichment after successful event creation when start/end location information is sufficient.
- If calendar publication fails after Work data is written, use a transaction where supported or a recoverable outbox/status pattern; never report success for a partial import without explaining it.

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
- approval creates exactly one Work shift and one linked calendar event
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
7. Add approval, calendar publication, travel trigger and undo.
8. Run full local and hosted-schema tests; review diff before deployment.

## 13. Explicit non-goals for the first release

- Employer/HR system integrations.
- Automatic publishing without user approval.
- Retaining uploaded rota documents as a permanent archive.
- Payroll, timesheets or overtime calculations.
- Sharing or collaborative rota management.
- Learning from user corrections across accounts without an explicit, privacy-reviewed opt-in.
