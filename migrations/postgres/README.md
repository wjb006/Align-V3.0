# PostgreSQL schema setup

Use a new Neon database dedicated to this Align V3.0 installation. Never apply a fresh-install schema to an existing database.

## Fresh installation

For a genuinely new database, apply **`fresh_v3_schema.sql`** once using the Neon SQL Editor or a trusted PostgreSQL client. It creates separate `align_auth` and `align_owner` schemas, includes the retained V3 organiser, configurable Studio, Asset Studio and Travel tables, and deliberately omits the retired shift-planner table family. It contains no user accounts, credentials, settings or planner records.

The older `bootstrap.sql` is a metadata-only compatibility snapshot retained for isolated legacy integration tests. **Do not use it to provision a new V3 installation.**

The Owner account is created at startup from the private `ALIGN_PREVIEW_PASSWORD` setting. New tester invitations create a separate `align_tester_<user-id>` schema from the same reviewed fresh V3 DDL. Public request data never determines SQL statements or table names.

## Local SQLite development

New local databases use the shift-free `schema_v3.sqlite.sql` and do not run legacy shift seeding or triggers. An existing SQLite file that contains any legacy schedule table remains on the compatibility initializer so its stored records are preserved. Active V3 Home, availability, Travel refresh, calendar, and iCloud sync flows no longer query those retired tables.

## Existing hosted schemas

For an existing database, apply migrations 150–154 to the Owner schema and each existing tester schema that uses those features. Apply migration 155 **once per database** with `align_auth,align_owner` on the PostgreSQL `search_path`; it provisions shared HERE transit quota storage in `align_auth` and records the marker in `align_owner`. These are explicit, idempotent provisioning steps; the running application never creates or alters hosted tables and existing rows are preserved. Migration 153 adds the imported-event destination column and persistent Travel tables; migration 154 provisions contacts and favourites.

The CI fixture at `tests/hosted_schema_fixture.sql` intentionally retains legacy schedule tables to verify compatibility and data preservation. The dedicated fresh-schema integration test uses `fresh_v3_schema.sql` and asserts that startup works without those tables. Keep both paths distinct.
