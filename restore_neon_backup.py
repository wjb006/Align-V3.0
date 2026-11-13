"""Restore an Align backup into a database you name.

This does not run against production unless you pass --confirm-restore.
It inserts rows and stops if a table already contains data. Create a Neon
branch or an empty database first. See docs/BACKUP_RESTORE.md.
"""
import argparse
import gzip
import json
import os
import sys
from urllib.parse import urlparse


def load(path):
    with gzip.open(path, 'rt', encoding='utf-8') as handle:
        data = json.load(handle)
    if 'tables' not in data:
        raise ValueError('This file is not an Align backup.')
    return data


def commands(data):
    items = []
    for key, table in data['tables'].items():
        schema = table.get('schema') or key.split('.', 1)[0]
        name = table.get('table') or key.split('.', 1)[-1]
        items.append((schema, name, list(table['columns']), list(table['rows'])))
    return items


def safe_target(dsn):
    parsed = urlparse(dsn)
    host = parsed.hostname or 'unknown-host'
    port = f':{parsed.port}' if parsed.port else ''
    name = parsed.path.lstrip('/') or 'database'
    return f'{host}{port}/{name}'


def apply(connection, data):
    """Insert every backed-up table. Refuse a table that already has rows."""
    applied = []
    with connection.cursor() as cursor:
        for schema, name, columns, rows in commands(data):
            quoted_schema = '"' + schema.replace('"', '""') + '"'
            quoted_name = '"' + name.replace('"', '""') + '"'
            cursor.execute(f'SELECT COUNT(*) FROM {quoted_schema}.{quoted_name}')
            count = cursor.fetchone()[0]
            if count:
                raise RuntimeError(f'{schema}.{name} already has rows. Restore into an empty database.')
            if not rows:
                applied.append((f'{schema}.{name}', 0))
                continue
            column_sql = ', '.join('"' + column.replace('"', '""') + '"' for column in columns)
            marks = ', '.join(['%s'] * len(columns))
            cursor.executemany(
                f'INSERT INTO {quoted_schema}.{quoted_name} ({column_sql}) VALUES ({marks})',
                rows,
            )
            applied.append((f'{schema}.{name}', len(rows)))
    connection.commit()
    return applied


def main(argv=None):
    parser = argparse.ArgumentParser(description='Restore an Align backup into an empty database.')
    parser.add_argument('backup')
    parser.add_argument('--confirm-restore', action='store_true')
    args = parser.parse_args(argv)
    dsn = os.environ.get('DATABASE_URL', '').strip()
    if not args.confirm_restore:
        print('Refusing to restore. Re-run with --confirm-restore after reading docs/BACKUP_RESTORE.md.', file=sys.stderr)
        return 2
    if not dsn:
        print('DATABASE_URL is not set.', file=sys.stderr)
        return 2
    print(f'Restoring into {safe_target(dsn)}')
    import psycopg
    data = load(args.backup)
    with psycopg.connect(dsn, connect_timeout=20) as connection:
        applied = apply(connection, data)
    for name, count in applied:
        print(f'{name} {count} rows')
    return 0


if __name__ == '__main__':
    sys.exit(main())
