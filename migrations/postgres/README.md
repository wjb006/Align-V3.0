# PostgreSQL schema setup

Use a new Neon database dedicated to this Align installation. Do not run this bootstrap against the existing Align database.

For a new database, apply `bootstrap.sql` once using the Neon SQL Editor or a trusted PostgreSQL client. It creates `align_auth` and `align_owner` with no user rows, credentials, settings or planner records. Render's `DATABASE_URL` must point to that database before the service starts.

The Owner account is created at startup from the private `ALIGN_PREVIEW_PASSWORD` setting. New tester invitations create a separate `align_tester_<user-id>` schema from the reviewed static DDL. Public request data never determines SQL statements or table names.

For an existing schema, apply `150_calendar_links.postgres.sql` and `151_sections.postgres.sql` with the target schema on the PostgreSQL `search_path`. Repeat for each tester schema. The calendar migration copies existing section calendar links before the new code reads them. The bootstrap script already includes both migrations and their markers.

The CI fixture at `tests/hosted_schema_fixture.sql` mirrors the empty hosted schema for isolated PostgreSQL integration tests. Keep it in sync with the bootstrap and numbered migration files.
