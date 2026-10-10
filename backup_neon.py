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


def export_tables(connection):
    tables = {}
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name"
        )
        names = [row[0] for row in cursor.fetchall()]
        for name in names:
            cursor.execute('SELECT * FROM "' + name.replace('"', '""') + '"')
            columns = [column.name for column in cursor.description]
            tables[name] = {"columns": columns, "rows": [[_plain(v) for v in row] for row in cursor.fetchall()]}
    return tables


def prune(directory, keep):
    files = sorted(directory.glob("align-neon-*.json.gz"))
    for old in files[:-keep] if keep > 0 else []:
        old.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", default=os.environ.get("ALIGN_LOCAL_BACKUP_DIR", "Backups"))
    parser.add_argument("--keep", type=int, default=14, help="newest backups to keep (0 = keep all)")
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
