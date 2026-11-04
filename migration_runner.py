"""Transactional migrations with SQLite online backups; no live path defaults."""
from datetime import datetime, timezone
import logging
from pathlib import Path
import sqlite3
import uuid
from sqlite_support import connect
from align_paths import source_root

ROOT = source_root() / 'migrations'
ID = '149_asset_studio'
LOG = logging.getLogger(__name__)

def statements(sql):
    pending = ''
    for char in sql:
        pending += char
        if char == ';' and sqlite3.complete_statement(pending):
            yield pending
            pending = ''
    if any(line.strip() and not line.lstrip().startswith('--') for line in pending.splitlines()):
        raise ValueError('Incomplete SQL statement')

def verify(c, folder=ROOT):
    if c.execute('PRAGMA foreign_keys').fetchone()[0] != 1 or c.execute('PRAGMA foreign_key_check').fetchall():
        raise RuntimeError('STOP: foreign key integrity')
    for query in statements((folder/'POST_MIGRATION_CHECKS.sql').read_text(encoding='utf-8-sig')):
        for name, violations in c.execute(query):
            if violations:
                raise RuntimeError(f'STOP: {name}; expected 0 violations, found {violations}')

def backup(database):
    database = Path(database).resolve()
    target = database.with_name(database.name + '.backup_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '_' + uuid.uuid4().hex[:8])
    with target.open('xb'):
        pass
    with connect(database.as_uri() + '?mode=ro', uri=True) as source, connect(target) as dest:
        source.backup(dest)
        if dest.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('Backup integrity check failed')
    return target

def migrate(database, folder=ROOT):
    folder = Path(folder)
    with connect(database) as c:
        c.execute('BEGIN IMMEDIATE')
        marker_table = c.execute("SELECT 1 FROM sqlite_master WHERE name='schema_migrations'").fetchone()
        if marker_table and c.execute('SELECT 1 FROM schema_migrations WHERE migration_id=?', (ID,)).fetchone():
            verify(c, folder)
            return {'status': 'skipped'}
        saved = backup(database)
        try:
            if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name IN ('assets','asset_categories','asset_variants','asset_usage_rules','asset_audit_log')").fetchone():
                raise RuntimeError('STOP: unmarked Asset Studio tables; reconcile separately')
            c.execute('CREATE TABLE IF NOT EXISTS schema_migrations(migration_id TEXT PRIMARY KEY, applied_at TEXT NOT NULL)')
            for sql in statements((folder/'149_asset_studio.sql').read_text(encoding='utf-8-sig')):
                c.execute(sql)
            c.execute('INSERT INTO schema_migrations VALUES (?,CURRENT_TIMESTAMP)', (ID,))
            verify(c, folder)
            c.commit()
            verify(c, folder)
            return {'status': 'applied', 'backup': str(saved)}
        except Exception:
            c.rollback()
            LOG.exception('Asset Studio migration failed; backup: %s', saved)
            raise

def rollback(database, folder=ROOT):
    with connect(database) as c:
        if c.in_transaction:
            raise RuntimeError('Rollback requires no active transaction')
        saved = backup(database)
        try:
            c.execute('PRAGMA foreign_keys=OFF')
            if c.execute('PRAGMA foreign_keys').fetchone()[0] != 0:
                raise RuntimeError('Could not disable foreign keys')
            c.execute('BEGIN IMMEDIATE')
            for sql in statements((Path(folder)/'149_asset_studio_rollback.sql').read_text(encoding='utf-8-sig')):
                c.execute(sql)
            if c.execute('PRAGMA foreign_key_check').fetchall():
                raise RuntimeError('Rollback leaves foreign key violations')
            c.commit()
        except Exception:
            c.rollback()
            LOG.exception('Asset rollback failed; backup: %s', saved)
            raise
        finally:
            c.execute('PRAGMA foreign_keys=ON')
        if c.execute('PRAGMA foreign_keys').fetchone()[0] != 1 or c.execute('PRAGMA foreign_key_check').fetchall():
            raise RuntimeError('Rollback verification failed')
        return {'status':'rolled_back', 'backup':str(saved)}

def upgrade(database):
    result=migrate(database)
    with connect(database) as c:
        c.execute('BEGIN IMMEDIATE')
        if not c.execute("SELECT 1 FROM schema_migrations WHERE migration_id='149_transport'").fetchone():
            backup(database)
            for sql in statements((ROOT/'149_transport.sql').read_text(encoding='utf-8')):
                c.execute(sql)
            c.execute("INSERT INTO schema_migrations VALUES('149_transport',CURRENT_TIMESTAMP)")
        if not c.execute("SELECT 1 FROM schema_migrations WHERE migration_id='154_user_favourites_contacts'").fetchone():
            backup(database)
            for sql in statements((ROOT/'154_user_favourites_contacts.sql').read_text(encoding='utf-8-sig')):
                c.execute(sql)
            c.execute("INSERT INTO schema_migrations VALUES('154_user_favourites_contacts',CURRENT_TIMESTAMP)")
    ensure_work_rota_schema(database, folder=ROOT)
    ensure_section_guide_schema(database, folder=ROOT)
    return result


def ensure_work_rota_schema(database, folder=ROOT):
    """Add rota review tables and shift provenance for an existing SQLite file.

    schema_v3.sqlite.sql is reapplied on startup, so the new shifts column cannot
    live there as an unconditional ALTER. This step is idempotent.
    """
    folder = Path(folder)
    rota_id = '157_work_rota_import'
    with connect(database) as probe:
        ready = _rota_schema_ready(probe)
        marked = False
        if probe.execute("SELECT 1 FROM sqlite_master WHERE name='schema_migrations'").fetchone():
            marked = bool(probe.execute(
                'SELECT 1 FROM schema_migrations WHERE migration_id=?', (rota_id,)
            ).fetchone())
        needs_column = False
        if probe.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='shifts'").fetchone():
            columns = {row[1] for row in probe.execute('PRAGMA table_info(shifts)')}
            needs_column = 'source_import_entry_id' not in columns
    if ready and marked and not needs_column:
        return {'status': 'skipped'}
    if needs_column:
        backup(database)
    with connect(database) as connection:
        connection.execute('BEGIN IMMEDIATE')
        connection.execute(
            'CREATE TABLE IF NOT EXISTS schema_migrations(migration_id TEXT PRIMARY KEY, applied_at TEXT NOT NULL)'
        )
        if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='shifts'").fetchone():
            columns = {row[1] for row in connection.execute('PRAGMA table_info(shifts)')}
            if 'source_import_entry_id' not in columns:
                connection.execute('ALTER TABLE shifts ADD COLUMN source_import_entry_id TEXT')
        for statement in statements((folder / '157_work_rota_import.sql').read_text(encoding='utf-8')):
            connection.execute(statement)
        if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='shifts'").fetchone():
            connection.execute(
                'CREATE UNIQUE INDEX IF NOT EXISTS idx_shifts_source_import_entry ON shifts(source_import_entry_id)'
            )
        connection.execute(
            'INSERT OR IGNORE INTO schema_migrations(migration_id,applied_at) VALUES (?,CURRENT_TIMESTAMP)',
            (rota_id,),
        )
        connection.commit()
    return {'status': 'applied'}


def _rota_schema_ready(connection):
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {'work_rota_imports', 'work_rota_entries', 'work_rota_approvals', 'shifts'} <= tables:
        return False
    columns = {row[1] for row in connection.execute('PRAGMA table_info(shifts)')}
    return 'source_import_entry_id' in columns


def upgrade_planner_schema(database, folder=ROOT):
    """Apply planner migrations after schema.sql has created its base tables."""
    folder = Path(folder)
    applied = []
    with connect(database) as c:
        c.execute('CREATE TABLE IF NOT EXISTS schema_migrations(migration_id TEXT PRIMARY KEY, applied_at TEXT NOT NULL)')
        if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='organiser_sections'").fetchone():
            raise RuntimeError('Base planner schema must be installed before planner migrations.')
        for migration_id in ('150_calendar_links', '151_sections'):
            if c.execute('SELECT 1 FROM schema_migrations WHERE migration_id=?', (migration_id,)).fetchone():
                continue
            c.execute('BEGIN IMMEDIATE')
            if migration_id == '150_calendar_links':
                columns = {row[1] for row in c.execute('PRAGMA table_info(calendar_sources)')}
                for name in ('target_kind', 'target_key'):
                    if name not in columns:
                        c.execute(f"ALTER TABLE calendar_sources ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")
                for statement in statements((folder / '150_calendar_links.sql').read_text(encoding='utf-8-sig')):
                    c.execute(statement)
                c.execute("""INSERT OR IGNORE INTO calendar_links
                    (target_kind,target_key,calendar_url,calendar_name,import_enabled,export_enabled)
                    SELECT 'organiser_section',CAST(id AS TEXT),calendar_url,calendar_name,import_enabled,export_enabled
                    FROM organiser_sections WHERE calendar_url<>''""")
                c.execute("""UPDATE calendar_sources SET target_kind='organiser_section',target_key=CAST(section_id AS TEXT)
                    WHERE section_id IS NOT NULL AND target_kind=''""")
            else:
                for statement in statements((folder / '151_sections.sql').read_text(encoding='utf-8-sig')):
                    c.execute(statement)
            c.execute('INSERT INTO schema_migrations VALUES (?,CURRENT_TIMESTAMP)', (migration_id,))
            c.commit()
            applied.append(migration_id)
    guide = ensure_section_guide_schema(database, folder=folder)
    if guide.get('status') == 'applied':
        applied.append('158_section_guides')
    return {'status': 'applied' if applied else 'skipped', 'migrations': applied}


def ensure_section_guide_schema(database, folder=ROOT):
    """Add saved places, labels and section defaults.

    schema_v3.sqlite.sql is reapplied on startup, so the tables are created with
    IF NOT EXISTS there and in the numbered migration. No ALTER is repeated.
    """
    folder = Path(folder)
    guide_id = '158_section_guides'
    needed = {'saved_places', 'planner_labels', 'section_defaults', 'organiser_event_details'}
    with connect(database) as probe:
        tables = {row[0] for row in probe.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        marked = False
        if 'schema_migrations' in tables:
            marked = bool(probe.execute(
                'SELECT 1 FROM schema_migrations WHERE migration_id=?', (guide_id,)
            ).fetchone())
        if needed <= tables and marked:
            return {'status': 'skipped'}
        if 'organiser_sections' not in tables or 'organiser_events' not in tables:
            return {'status': 'waiting'}
    with connect(database) as connection:
        connection.execute('BEGIN IMMEDIATE')
        connection.execute(
            'CREATE TABLE IF NOT EXISTS schema_migrations(migration_id TEXT PRIMARY KEY, applied_at TEXT NOT NULL)'
        )
        for statement in statements((folder / '158_section_guides.sql').read_text(encoding='utf-8')):
            connection.execute(statement)
        connection.execute(
            'INSERT OR IGNORE INTO schema_migrations(migration_id,applied_at) VALUES (?,CURRENT_TIMESTAMP)',
            (guide_id,),
        )
        connection.commit()
    return {'status': 'applied'}
