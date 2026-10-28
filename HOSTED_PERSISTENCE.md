# Hosted Owner persistence

`ALIGN_DATABASE_BACKEND=postgres` selects the existing `DATABASE_URL` via the
shared connection boundary. Only `beta_users.sqlite3` (align_auth) and
`align.sqlite3` (align_owner) are supported. Missing connectivity, missing tables,
unsupported database paths and tester provisioning fail rather than creating
local databases. SQLite remains the default locally. The existing Render
`ALIGN_HOSTING_MODE=disposable-preview` flag is retained for deployment compatibility;
the backend flag determines durable versus disposable storage.

Hosted startup is validation-only: it never creates or alters hosted schema. New PostgreSQL databases use `migrations/postgres/fresh_v3_schema.sql`, which includes the restored shift planner and records `156_shift_planner`. Existing schemas require the reviewed explicit numbered migrations documented in `migrations/postgres/README.md`, including migration 156 where the planner is missing. Fresh local SQLite databases use `schema_v3.sqlite.sql`. An older SQLite file with schedule tables but no `156_shift_planner` marker stays on the preservation path. `bootstrap.sql` and `tests/hosted_schema_fixture.sql` are compatibility fixtures, not the fresh provisioning source. Startup validation requires the planner tables. Contacts/favourites are provisioned by migration 154. Shared HERE transit quota storage is provisioned once in `align_auth` by migration 155, with its marker in `align_owner`; quota requests never create the table. New tester schemas record both `155_here_transit_usage` and `156_shift_planner`.

The adapter deliberately implements only the SQL used by Align, rejects runtime DDL/scripts, and supports named/positional rows, parameter binding, conflict handling, generated IDs and transaction closure.

Hosted bootstrap locks the Owner operation, requires at most one existing Owner,
and only sets a password when absent. An existing password requires no bootstrap
environment password. For an absent password, ALIGN_PREVIEW_PASSWORD must meet the
existing validation and have at least 20 characters. Startup confirms exactly one
Owner and executes queries against both schemas before reporting Neon ready.

Tester storage, asset-file durability and encryption-key provisioning are not
implemented by this change. Local database/key files are untracked and ignored;
this does not erase prior Git history. Review existing Render secret provisioning
before using stored email/iCloud credentials: local generated keys are disposable.

## Tests

Run `python -m pytest -q`. The workflow also starts an isolated Postgres 18 service
and sets ALIGN_TEST_POSTGRES_URL to a loopback database named align_persistence_test.
The integration fixture requires a fresh database and refuses remote URLs. It tests
real queries, Owner password/timestamp preservation, two hosted startups, Inbox
insert/read/delete persistence, generated IDs, conflicts, sessions and rollback.

## Review and redeploy verification

Do not merge or deploy until checks are green and the PR diff has been reviewed.
Keep DATABASE_URL and passwords in Render secrets, never in logs or this repository.

1. Immediately before deploy, privately save the following baseline. Record the
   Owner user_id, created_at and password_set_at; do not export password hashes.

   ```sql
   SELECT user_id, created_at, password_set_at,
          COALESCE(password_hash,'') <> '' AS password_is_set
   FROM align_auth.beta_users WHERE is_owner=1;
   SELECT 'owners' AS metric, COUNT(*) FROM align_auth.beta_users WHERE is_owner=1
   UNION ALL SELECT 'inbox', COUNT(*) FROM align_owner.personal_items
   UNION ALL SELECT 'settings', COUNT(*) FROM align_owner.settings
   UNION ALL SELECT 'sections', COUNT(*) FROM align_owner.organiser_sections;
   ```

2. After approved deployment, require the startup log to say both align_auth and
   align_owner queries were verified. Check the hosted health endpoint and sign in
   with the existing Owner password. Repeat the baseline SQL: exactly one Owner,
   unchanged user_id/created_at/password_set_at for an already-set password, and
   unchanged planner counts in the absence of concurrent user edits.
3. In the hosted Inbox, create a uniquely named temporary note such as
   `Persistence verification <UTC timestamp>`. Query align_owner.personal_items
   by its exact title, save its id, and confirm its title and kind.
4. Perform one controlled redeploy of the same reviewed commit. Recheck both-schema
   startup success, the Owner baseline, and the saved note id in Neon and the UI.
5. Delete the temporary note through the hosted Inbox. Verify
   `SELECT COUNT(*) FROM align_owner.personal_items WHERE id='<saved id>';`
   returns zero and the Inbox count returns to baseline (allowing for concurrent edits).

If any step fails, stop release acceptance. Preserve the baseline and logs without
secrets; do not reset the Owner or switch to disposable SQLite as a workaround.


## Persistent saved-credential encryption

Hosted Postgres requires ALIGN_CREDENTIAL_KEY, a Fernet key stored as a Render secret environment variable. Generate it once with cryptography.fernet.Fernet.generate_key(), keep it unchanged across redeploys, and never commit or log it. Reuse the original beta_secret.key value if it is recoverable; a newly generated key cannot decrypt existing credentials encrypted with a lost key. Those accounts must reconnect iCloud. Planner/calendar rows and the old encrypted credential rows are retained until the user reconnects or disconnects.

Local SQLite continues using its existing beta_secret.key unless an environment key is explicitly supplied. Missing/invalid hosted keys fail credential writes instead of silently creating an ephemeral key. Unreadable saved iCloud credentials produce a reconnect notice without blocking planner bootstrap. The same persistent key protects saved Outlook tokens; an old token encrypted with a lost key will also require reconnection.
