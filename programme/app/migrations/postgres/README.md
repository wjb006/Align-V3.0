# PostgreSQL schema setup

Use a new Neon database dedicated to this Align V3.0 installation. Never apply a fresh-install schema to an existing database.

## Fresh installation

For a genuinely new database, apply **`fresh_v3_schema.sql`** once using the Neon SQL Editor or a trusted PostgreSQL client. It creates separate `align_auth` and `align_owner` schemas and includes the organiser, Studio, Asset Studio, Travel, and restored shift-planner tables. It records migrations through `156_shift_planner`. It contains no user accounts, credentials, settings, or planner records.

The older `bootstrap.sql` is a metadata-only compatibility snapshot retained for isolated legacy integration tests. **Do not use it to provision a new V3 installation.**

The Owner account is created at startup from the private `ALIGN_PREVIEW_PASSWORD` setting. New tester invitations create a separate `align_tester_<user-id>` schema from the same reviewed fresh V3 DDL. Public request data never determines SQL statements or table names.

## Local SQLite development

New local databases use `schema_v3.sqlite.sql`, which includes the restored shift planner and records `156_shift_planner`. An older SQLite file that has schedule tables but not that marker stays on the compatibility initializer so its stored records are preserved.

## Existing hosted schemas

For an existing database, apply migrations 150–156 to the Owner schema and each existing tester schema that uses those features. Apply migration 155 **once per database** with `align_auth,align_owner` on the PostgreSQL `search_path`; it provisions shared HERE transit quota storage in `align_auth` and records the marker in `align_owner`. Apply migration 156 to restore the shift planner on a database created before that restoration. These are explicit, idempotent provisioning steps; the running application never creates or alters hosted tables and existing rows are preserved. Migration 153 adds the imported-event destination column and persistent Travel tables; migration 154 provisions contacts and favourites.

The CI fixture at `tests/hosted_schema_fixture.sql` includes the planner tables so compatibility tests can preserve schedule data. The fresh-schema integration test uses `fresh_v3_schema.sql`, which also includes those tables and the `156_shift_planner` marker. Hosted startup validates them and does not create them.
