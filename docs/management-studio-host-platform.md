# Align Management Studio — Unified Host Platform

## Purpose

Management Studio is the control centre for the Align platform. It should be installable as a Windows desktop application while the user-facing Align app continues to run online at the public domain and keeps its data in the configured hosted database.

## Product areas

### App
- Open the real Align user-facing application from inside the desktop shell.
- Use the same authenticated application and API as the hosted app; do not copy production data into a separate desktop database.
- Clearly identify whether the view is Production or Local/Test.
- Keep offline behaviour in the user-facing app; sync when connectivity returns according to the app's existing sync rules.

### Studio
- Preserve the existing Management Studio builder, design controls, previews, history and publishing workflow.
- Keep drafts and published configuration behaviour unchanged.
- Show an embedded app preview where feasible, with a separate action to open the full app.

### Host
- Show service availability, application/build version, database connectivity, last backup and deployment status.
- Show transport/OTP provider readiness and feed/graph timestamps where existing health endpoints can report them.
- Offer guarded actions for backups, restore, rebuild and deployment only after explicit confirmation and authorization.
- Never display secrets, database URLs, API keys, tokens or recovery codes. Show configured/not configured and masked status only.
- Preserve existing transport and OTP settings; never silently rewrite environment variables or production data.

## Architecture and safety boundaries

1. The desktop client is a shell around the existing web application, not a second implementation of Align.
2. Production remains hosted and available when the user's PC is off.
3. Production requests use the canonical public origin and existing server-side authentication. Do not store production credentials in the desktop package.
4. Local development/test uses a separate origin and database, and is visibly labelled. Never fall back from production to a local database without telling the user.
5. Host status and actions must be backed by server-side endpoints with authorization checks. The UI must not infer health from a successful page load alone.
6. Existing Management Studio routes and APIs must continue working. New shell navigation must not bypass or weaken authorization.
7. The shell should use a maintained desktop webview/runtime and a signed/packageable installer; keep source, configuration, logs and user data outside the executable.
8. Do not deploy this feature branch automatically to production. Merge only after local tests, hosted smoke tests and owner approval.

## Delivery sequence

1. Add the App / Studio / Host shell navigation on a feature branch and preserve the existing Studio.
2. Wire App to the canonical app route and make environment identity visible.
3. Implement Host read-only health panels using existing, authenticated health/status APIs.
4. Add guarded Host actions only after confirming backup/restore/rebuild endpoints and permissions.
5. Package the desktop shell and verify installation, update behaviour, startup and authentication on Windows.
6. Test the live domain, persistence across restarts, offline user-facing behaviour, and transport/OTP readiness without changing production settings.

## Current implementation note

This document records the intended architecture and safety boundaries. It does not claim that the desktop shell, embedded App view, Host dashboard, installer, or any health/action endpoints have been implemented or tested yet.
