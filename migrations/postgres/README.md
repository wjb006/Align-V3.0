# PostgreSQL schema setup

Use a new Neon database dedicated to this Align V3.0 installation. Never apply a fresh-install schema to an existing database.

## Fresh installation

For a genuinely new database, apply **`fresh_v3_schema.sql`** once using the Neon SQL Editor or a trusted PostgreSQL client. It creates separate `align_auth` and `align_owner` schemas, includes the retained V3 organiser, configurable Studio, Asset Studio and Travel tables, and deliberately omits the retired shift-planner table family. It contains no user accounts, credentials, settings or planner records.

The older `bootstrap.sql` is a metadata-only compatibility snapshot retained for isolated legacy integration tests. **Do not use it to provision a new V3 installation.**

The Owner account is created at startup from the private `ALIGN_PREVIEW_PASSWORD` setting. New tester invitations create a separate `align_tester_<user-id>` schema from the same reviewed fresh V3 DDL. Public request data never determines SQL statements or table names.

## Existing hosted schemas

For an existing schema that needs the newer retained features, apply `150_calendar_links.postgres.sql`, `151_sections.postgres.sql`, `152_personal_item_calendars.postgres.sql`, and `153_hosted_travel_and_calendar_location.postgres.sql` with the target schema on the PostgreSQL `search_path`. Repeat for the Owner schema and each tester schema as applicable. These are explicit provisioning steps; the running application never creates or alters hosted tables. Migration 153 adds the imported-event destination column and persistent Travel tables, and seeds default Travel preferences without dropping or truncating data.

The CI fixture at `tests/hosted_schema_fixture.sql` intentionally retains legacy schedule tables to verify compatibility and data preservation. The dedicated fresh-schema integration test uses `fresh_v3_schema.sql` and asserts that startup works without those tables. Keep both paths distinct.
