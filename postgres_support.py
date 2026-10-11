"""Narrow SQLite call compatibility for the existing, provisioned Neon schemas.

No DDL, schema creation, data copying or fallback to local files is permitted.
"""
import os
import re
import sqlite3
from datetime import date, datetime
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.pq import TransactionStatus
from psycopg.conninfo import conninfo_to_dict


class Row:
    def __init__(self, names, values):
        self.names = names
        self.values = tuple(v.isoformat() if isinstance(v, (date, datetime)) else v for v in values)

    def keys(self):
        return self.names

    def __getitem__(self, key):
        return self.values[self.names.index(key) if isinstance(key, str) else key]

    def __iter__(self):
        return iter(self.values)

    def __len__(self):
        return len(self.values)


class Result:
    def __init__(self, rows=(), rowcount=-1, lastrowid=None):
        self.rows = iter(rows)
        self.rowcount = rowcount
        self.lastrowid = lastrowid

    def fetchone(self):
        return next(self.rows, None)

    def fetchall(self):
        return list(self.rows)

    def __iter__(self):
        return self.rows


# Protect quoted strings/identifiers and comments before translating code tokens.
TOKENS = re.compile(r"('(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|--[^\n]*(?:\n|$)|/\*.*?\*/)", re.S)


def translate(sql):
    parts = TOKENS.split(sql.strip().rstrip(';'))
    for index in range(0, len(parts), 2):
        part = re.sub(r'\bBEGIN\s+IMMEDIATE\b', 'BEGIN', parts[index], flags=re.I)
        part = re.sub(r'\b(\w+)\s*=\s*\?\s+COLLATE\s+NOCASE\b', r'LOWER(\1)=LOWER(?)', part, flags=re.I)
        parts[index] = part.replace('%', '%%').replace('?', '%s')
    for index in range(1, len(parts), 2):
        parts[index] = parts[index].replace('%', '%%')
    return ''.join(parts)


def schema_for(path):
    path = Path(path)
    # Tester storage paths are strictly per-user. Never let a file placed in
    # beta_data route to the shared auth or owner schema by basename.
    if path.parent.name == 'beta_data':
        if re.fullmatch(r'[a-f0-9]{24}\.sqlite3', path.name, re.I):
            return 'align_tester_' + path.stem.lower()
        raise RuntimeError('Unsupported hosted database path; refusing local storage')
    schema = {'beta_users.sqlite3': 'align_auth', 'align.sqlite3': 'align_owner'}.get(path.name)
    if schema:
        return schema
    raise RuntimeError('Unsupported hosted database path; refusing local storage')


class Connection:
    # Callers set sqlite3.Row; this facade always provides its equivalent.
    row_factory = None

    def __init__(self, raw, schema):
        self.raw = raw
        self.schema = schema
        self._identities = {}

    def execute(self, sql, parameters=()):
        if re.match(r'^\s*PRAGMA\s+(foreign_keys\s*=\s*ON|busy_timeout\s*=\s*5000)\s*;?\s*$', sql, re.I):
            return Result()
        info = re.fullmatch(r'\s*PRAGMA\s+table_info\((\w+)\)\s*;?\s*', sql, re.I)
        if info:
            return self._run('''SELECT ordinal_position-1 AS cid, column_name AS name,
                data_type AS type, (is_nullable='NO')::int AS "notnull",
                column_default AS dflt_value, 0 AS pk
                FROM information_schema.columns WHERE table_schema=%s AND table_name=%s
                ORDER BY ordinal_position''', (self.schema, info[1]))
        if re.match(r'^\s*(PRAGMA|CREATE|ALTER|DROP|VACUUM|ATTACH)\b', sql, re.I):
            raise sqlite3.NotSupportedError('SQLite schema operations are disabled in hosted Postgres mode')
        statement = translate(sql)
        ignore = re.match(r'INSERT\s+OR\s+IGNORE\s+', statement, re.I)
        replace = re.match(r'INSERT\s+OR\s+REPLACE\s+INTO\s+(\w+)\s*\(([^)]+)\)', statement, re.I)
        if ignore:
            statement = re.sub(r'^INSERT\s+OR\s+IGNORE', 'INSERT', statement, flags=re.I) + ' ON CONFLICT DO NOTHING'
        if replace:
            keys = {'beta_sessions': 'session_hash', 'beta_idempotency': 'key_hash'}
            key = keys.get(replace[1].lower())
            if not key:
                raise sqlite3.NotSupportedError('Unsupported hosted INSERT OR REPLACE')
            columns = [c.strip() for c in replace[2].split(',')]
            if any(not re.fullmatch(r'\w+', c) for c in columns):
                raise sqlite3.NotSupportedError('Unsupported replacement columns')
            statement = re.sub(r'^INSERT\s+OR\s+REPLACE', 'INSERT', statement, flags=re.I)
            statement += f' ON CONFLICT ({key}) DO UPDATE SET ' + ', '.join(f'{c}=EXCLUDED.{c}' for c in columns if c != key)
        inserted = re.match(r'INSERT\s+INTO\s+(\w+)\b', statement, re.I)
        identity = None
        if inserted and not re.search(r'\bRETURNING\b', statement, re.I):
            table = inserted[1].lower()
            if table not in self._identities:
                result = self._run('''SELECT column_name FROM information_schema.columns
                    WHERE table_schema=%s AND table_name=%s
                    AND (is_identity='YES' OR column_default LIKE 'nextval(%%')''', (self.schema, table)).fetchone()
                self._identities[table] = result[0] if result else None
            identity = self._identities[table]
            if identity:
                statement += ' RETURNING "' + identity.replace('"', '""') + '"'
        result = self._run(statement, parameters)
        if identity:
            row = result.fetchone()
            result.lastrowid = row[0] if row else None
        return result

    def _configure_transaction(self, cursor):
        cursor.execute(
            sql.SQL('SET LOCAL search_path TO {}, pg_catalog').format(sql.Identifier(self.schema))
        )
        cursor.execute("SET LOCAL timezone TO 'UTC'")

    def _run(self, sql, parameters=()):
        try:
            with self.raw.cursor() as cursor:
                if self.raw.info.transaction_status == TransactionStatus.IDLE:
                    self._configure_transaction(cursor)
                cursor.execute(sql, parameters)
                names = tuple(col.name for col in cursor.description) if cursor.description else ()
                rows = [Row(names, row) for row in cursor.fetchall()] if names else []
                return Result(rows, cursor.rowcount)
        except psycopg.IntegrityError:
            raise sqlite3.IntegrityError('Hosted database constraint violation') from None
        except psycopg.Error:
            raise sqlite3.OperationalError('Hosted Postgres query failed; check schema compatibility and connectivity') from None

    def executemany(self, sql, parameters):
        count = 0
        for values in parameters:
            count += self.execute(sql, values).rowcount
        return Result(rowcount=count)

    def executescript(self, script):
        raise sqlite3.NotSupportedError('SQLite scripts are disabled in hosted Postgres mode')

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        self.raw.close()

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        try:
            if kind is None:
                self.commit()
            else:
                self.rollback()
        finally:
            self.close()


def _safe_dsn_summary(dsn):
    try:
        info = conninfo_to_dict(dsn)
    except Exception:
        return {'parsed': False}
    return {
        'parsed': True,
        'host': info.get('host'),
        'port': info.get('port') or '5432',
        'dbname': info.get('dbname'),
        'user': info.get('user'),
        'sslmode': info.get('sslmode'),
        'channel_binding': info.get('channel_binding'),
        'password_present': bool(info.get('password')),
    }


def _safe_connection_error(exc, dsn):
    # Driver messages can contain reformatted credentials, not only the exact DSN.
    # Log the exception class and allowlisted connection metadata instead.
    return 'Connection or transaction setup failed; upstream details suppressed.'



def connect(path):
    schema = schema_for(path)
    dsn = os.environ.get('DATABASE_URL', '').strip()
    if not dsn:
        raise RuntimeError('DATABASE_URL is required for hosted Postgres; refusing local storage')
    try:
        # Keep connection startup parameters minimal for pooled Neon/PgBouncer
        # endpoints. Apply schema/timezone inside the transaction instead.
        raw = psycopg.connect(dsn, connect_timeout=10)
        with raw.cursor() as cursor:
            cursor.execute(
                sql.SQL('SET LOCAL search_path TO {}, pg_catalog').format(sql.Identifier(schema))
            )
            cursor.execute("SET LOCAL timezone TO 'UTC'")
    except psycopg.Error as exc:
        try:
            raw.close()
        except (NameError, Exception):
            pass
        print(
            'POSTGRES CONNECT FAILED:',
            type(exc).__name__,
            _safe_connection_error(exc, dsn),
            _safe_dsn_summary(dsn),
            flush=True,
        )
        raise RuntimeError('Could not connect to hosted Postgres; see safe connection diagnostics above') from None
    return Connection(raw, schema)


def _bootstrap_statements():
    source = Path(__file__).resolve().parent / 'migrations' / 'postgres' / 'bootstrap.sql'
    pending = ''
    for char in source.read_text(encoding='utf-8-sig'):
        pending += char
        if char == ';':
            statement = pending.strip()
            pending = ''
            if statement:
                yield statement
    if pending.strip():
        raise RuntimeError('Hosted schema bootstrap contains an incomplete SQL statement.')


def provision_tester_schema(path):
    """Create an empty per-tester schema from the reviewed static PostgreSQL DDL."""
    schema = schema_for(path)
    if not schema.startswith('align_tester_'):
        raise RuntimeError('Only a tester schema can be provisioned by this operation.')
    dsn = os.environ.get('DATABASE_URL', '').strip()
    if not dsn:
        raise RuntimeError('DATABASE_URL is required to provision hosted tester storage.')
    try:
        with psycopg.connect(dsn, connect_timeout=10) as raw, raw.cursor() as cursor:
            cursor.execute('SELECT to_regnamespace(%s)', (schema,))
            if cursor.fetchone()[0]:
                return
            cursor.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            for statement in _bootstrap_statements():
                if statement.startswith('CREATE TABLE align_owner.') or statement.startswith('ALTER TABLE align_owner.'):
                    cursor.execute(statement.replace('align_owner.', sql.Identifier(schema).as_string(raw) + '.'))
            cursor.execute(sql.SQL("""INSERT INTO {}.schema_migrations(migration_id,applied_at)
                VALUES('149_asset_studio',CURRENT_TIMESTAMP),('149_transport',CURRENT_TIMESTAMP),
                ('150_calendar_links',CURRENT_TIMESTAMP),('151_sections',CURRENT_TIMESTAMP),
                ('152_personal_item_calendars',CURRENT_TIMESTAMP)
                ON CONFLICT(migration_id) DO NOTHING""").format(sql.Identifier(schema)))
    except psycopg.Error:
        raise RuntimeError('Could not create the tester schema from the reviewed hosted schema.') from None


def delete_tester_schema(path, user_id):
    """Delete one tester schema and its account row in the same database transaction."""
    schema = schema_for(path)
    if not schema.startswith('align_tester_'):
        raise RuntimeError('Only a tester schema can be deleted by this operation.')
    dsn = os.environ.get('DATABASE_URL', '').strip()
    if not dsn:
        raise RuntimeError('DATABASE_URL is required to delete hosted tester storage.')
    try:
        with psycopg.connect(dsn, connect_timeout=10) as raw, raw.cursor() as cursor:
            cursor.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))
            cursor.execute('DELETE FROM align_auth.beta_users WHERE user_id=%s', (user_id,))
    except psycopg.Error:
        raise RuntimeError('Could not delete the tester account and its hosted data.') from None


def validate_auth(c):
    for table in ('beta_users', 'beta_sessions', 'beta_invites', 'beta_password_resets',
                  'beta_idempotency', 'beta_audit_events', 'beta_rate_events',
                  'beta_feedback', 'beta_email_settings', 'beta_icloud_credentials'):
        c.execute(f'SELECT * FROM {table} LIMIT 0')
    c.execute('SELECT user_id, password_hash, password_set_at, created_at FROM beta_users LIMIT 0')


def validate_planner(c):
    for table in ('settings', 'personal_items', 'shifts', 'shift_templates', 'locations',
                  'shift_types', 'location_shift_types', 'annual_leave', 'alert_rules', 'alerts',
                  'calendar_sources', 'calendar_events', 'organiser_sections', 'organiser_events',
                  'parent_menu_branches', 'menu_branches', 'builder_config', 'builder_records',
                  'calendar_links', 'section_defs', 'section_fields',
                  'calendar_sync_state', 'icloud_config', 'icloud_items', 'shift_batches'):
        c.execute(f'SELECT * FROM {table} LIMIT 0')
    c.execute('SELECT layout_json FROM section_defs LIMIT 0')
    c.execute('SELECT applicable_days, sub_shift_type FROM shift_templates LIMIT 0')
    c.execute('SELECT calendar_id, calendar_event_id FROM personal_items LIMIT 0')


def prepare_calendar_locations():
    with connect('align.sqlite3') as c:
        c.raw.execute('SELECT pg_advisory_xact_lock(151202628)')
        c.raw.execute("ALTER TABLE calendar_events ADD COLUMN IF NOT EXISTS location TEXT NOT NULL DEFAULT ''")


def verify_hosted_storage():
    """Real data queries in both schemas, before the server announces readiness."""
    with connect('beta_users.sqlite3') as c:
        validate_auth(c)
        owners = c.execute('SELECT COUNT(*) FROM beta_users WHERE is_owner=1').fetchone()[0]
    with connect('align.sqlite3') as c:
        validate_planner(c)
        c.execute('SELECT COUNT(*) FROM personal_items').fetchone()
        c.execute('SELECT COUNT(*) FROM shifts').fetchone()
    if owners != 1:
        raise RuntimeError('Hosted startup requires exactly one Owner in align_auth')
