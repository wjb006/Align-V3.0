"""Transactional migrations with SQLite online backups; no live path defaults."""
from datetime import datetime, timezone
import logging
from pathlib import Path
import sqlite3
import uuid
from sqlite_support import connect

ROOT = Path(__file__).resolve().parent / 'migrations'
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
    return result


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
        return {'status': 'applied' if applied else 'skipped', 'migrations': applied}
