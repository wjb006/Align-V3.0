# Local database backups

In local SQLite mode, open **PC Admin → Settings → Local data & backups** to
download the current Align database or restore a previous Align `.sqlite3`
backup. The signed-in local Admin session is required. Files are limited to
100 MB.

A restore validates the SQLite integrity and required Align tables before
changing anything. Align then saves a complete pre-restore snapshot and replaces
the local database. In the organized installation, that safety copy is kept in
`Master\Backups`; other installations keep it in a `Backups` folder beside the
database. Align does not automatically remove these safety copies.

Disconnect iCloud on the PC before restoring. After restore, review the planner
and reconnect iCloud only after confirming the restored data. A backup contains
the SQLite database, including values stored in that database; it does not
bundle the app runtime or separate key files.

These controls are disabled when beta mode or a PostgreSQL backend is active.
They do not export or restore hosted Neon/Postgres data.
