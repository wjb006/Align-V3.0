"""Read-only export of the hosted (Neon) database to a local gzip JSON file.

Usage: set DATABASE_URL, then run `python backup_neon.py [--out DIR] [--keep N]`.
The file contains user data: keep it local and never commit it. Credentials are
never written to the output or printed.
"""
import argparse
import gzip
import json
import os
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path


def _plain(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"__bytes_hex__": bytes(value).hex()}
    return value


def _ident(name):
    return '"' + str(name).replace('"', '""') + '"'


def export_tables(connection):
    """Every ordinary schema, including align_auth, align_owner and align_tester_*."""
    tables = {}
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_type='BASE TABLE' AND table_schema NOT IN ('pg_catalog','information_schema') "
            "AND table_schema NOT LIKE 'pg_%' ORDER BY table_schema, table_name"
        )
        names = [(row[0], row[1]) for row in cursor.fetchall()]
        for schema, name in names:
            cursor.execute(f'SELECT * FROM {_ident(schema)}.{_ident(name)}')
            columns = [column.name for column in cursor.description]
            tables[f'{schema}.{name}'] = {
                "schema": schema, "table": name, "columns": columns,
                "rows": [[_plain(v) for v in row] for row in cursor.fetchall()],
            }
    return tables


def upload_backup(path):
    """Copy one backup into object storage when a bucket and credentials exist."""
    bucket = (os.environ.get('ALIGN_BACKUP_BUCKET') or '').strip()
    if not bucket or not os.environ.get('AWS_ACCESS_KEY_ID') or not os.environ.get('AWS_SECRET_ACCESS_KEY'):
        print('Object storage is not configured. The file is only on this machine.', file=sys.stderr)
        return False
    import boto3
    from botocore.config import Config
    client = boto3.client(
        's3',
        endpoint_url=(os.environ.get('AWS_ENDPOINT_URL_S3') or '').strip() or None,
        region_name=(os.environ.get('AWS_REGION') or 'auto').strip(),
        aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'],
        config=Config(signature_version='s3v4', s3={'addressing_style': 'path'}),
    )
    key = 'align-backups/' + path.name
    client.upload_file(str(path), bucket, key)
    print(f'Uploaded {key}')
    return True


def prune(directory, keep):
    files = sorted(directory.glob("align-neon-*.json.gz"))
    for old in files[:-keep] if keep > 0 else []:
        old.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", default=os.environ.get("ALIGN_LOCAL_BACKUP_DIR", "Backups"))
    parser.add_argument("--keep", type=int, default=14, help="newest backups to keep (0 = keep all)")
    parser.add_argument("--upload", action="store_true", help="also copy the file to ALIGN_BACKUP_BUCKET when credentials exist")
    args = parser.parse_args(argv)
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if not dsn:
        print("DATABASE_URL is not set; nothing was backed up.", file=sys.stderr)
        return 2
    import psycopg
    directory = Path(args.out)
    directory.mkdir(parents=True, exist_ok=True)
    try:
        with psycopg.connect(dsn, connect_timeout=20) as connection:
            connection.read_only = True
            tables = export_tables(connection)
    except psycopg.Error as error:
        print(f"Backup failed: {type(error).__name__}", file=sys.stderr)
        return 1
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = directory / f"align-neon-{stamp}.json.gz"
    temporary = target.with_suffix(".tmp")
    with gzip.open(temporary, "wt", encoding="utf-8") as handle:
        json.dump({"created": stamp, "tables": tables}, handle)
    temporary.replace(target)
    prune(directory, args.keep)
    rows = sum(len(t["rows"]) for t in tables.values())
    print(f"Saved {len(tables)} tables / {rows} rows to {target}")
    if args.upload:
        upload_backup(target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
