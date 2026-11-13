# Hosted database backup and restore

Nothing in this file creates a cron job, a Neon branch, or a bucket. Will applies the steps below when he wants them.

Align's hosted data is not in the `public` schema. Accounts are in `align_auth`, the owner planner is in `align_owner`, and each tester is in `align_tester_<id>`. `backup_neon.py` exports all of those schemas.

## Recommended: Neon snapshots

Neon already keeps point-in-time history for the project. This is the restore path that does not depend on Render's ephemeral disk.

1. In the Neon console, open the Align project and confirm the history window covers at least 7 days.
2. To rehearse a restore, create a branch from a timestamp or from the current parent. Do this on a branch, not by resetting production.
3. Point a temporary `DATABASE_URL` at that branch and run `python verify_neon_backup.py` only if you also have a JSON dump. For a Neon branch, open the branch and check `align_auth.beta_users` and `align_owner.organiser_events` row counts instead.
4. To make a branch the production database, that is a separate change of the Render `DATABASE_URL`. Do not do it as part of a rehearsal.

## Nightly JSON dump

`deploy/render-backup-cron.yaml` is a prepared cron. It is not included in the live `render.yaml`, so merging this branch does not create the job.

When Will wants the job:

1. Create a private bucket (or choose an existing one) and set `ALIGN_BACKUP_BUCKET`, `AWS_ENDPOINT_URL_S3`, `AWS_REGION`, `AWS_ACCESS_KEY_ID`, and `AWS_SECRET_ACCESS_KEY` on the cron service. Do not commit the values.
2. Set `DATABASE_URL` on the cron service to the same Neon connection the web service uses. Prefer the direct (non-pooled) connection for a full read.
3. Create the cron from `deploy/render-backup-cron.yaml` in the Render dashboard, or copy the service into a blueprint Will reviews first.
4. Schedule: `0 2 * * *` (02:00 UTC).
5. The command is `python backup_neon.py --out /tmp/align-backups --keep 7 --upload`.

Without the bucket credentials the script still writes a local file and says object storage is not configured. On Render that file disappears when the cron instance stops, so the upload is what makes the nightly dump durable.

The file contains account and planner data. Keep it private. It does not print the database URL or the storage keys.

## Restore a JSON dump

1. Create an empty Neon branch or a local Postgres database. Do not point `DATABASE_URL` at production.
2. Apply the Align schema to that empty database (`migrations/postgres/fresh_v3_schema.sql` and later additive migrations) so the tables exist and are empty.
3. Export `DATABASE_URL` for the empty database.
4. Run `python restore_neon_backup.py path/to/align-neon-....json.gz --confirm-restore`.
5. The script stops if any table already has rows.
6. Check `python verify_neon_backup.py path/to/align-neon-....json.gz` before trusting the file. That check uses a temporary SQLite file and does not touch Postgres.

`verify_neon_backup.py` loads the gzip into scratch SQLite and compares row counts. `restore_neon_backup.py` is the Postgres insert.
