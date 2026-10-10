"""Check a Neon backup file by loading it into a scratch local SQLite database.

Usage: python verify_neon_backup.py [BACKUP.json.gz]   (default: newest in Master/Backups/Neon)
Nothing is written to the live database; the scratch copy lives in a temp folder and is deleted.
"""
import gzip
import json
import sqlite3
import sys
import tempfile
from pathlib import Path


def newest(directory):
    files = sorted(Path(directory).glob("align-neon-*.json.gz"))
    return files[-1] if files else None


def verify(path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        data = json.load(handle)
    tables = data["tables"]
    report = {}
    with tempfile.TemporaryDirectory(prefix="align-verify-") as folder:
        connection = sqlite3.connect(Path(folder) / "scratch.sqlite3")
        for name, table in tables.items():
            columns = ", ".join('"' + c.replace('"', '""') + '"' for c in table["columns"])
            quoted = '"' + name.replace('"', '""') + '"'
            connection.execute(f"CREATE TABLE {quoted} ({columns})")
            marks = ",".join("?" * len(table["columns"]))
            rows = [[json.dumps(v) if isinstance(v, (dict, list)) else v for v in row] for row in table["rows"]]
            connection.executemany(f"INSERT INTO {quoted} VALUES ({marks})", rows)
            report[name] = (len(table["rows"]), connection.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0])
        connection.close()
    bad = [n for n, (expected, actual) in report.items() if expected != actual]
    return report, bad


def main(argv):
    if argv:
        path = Path(argv[0])
    else:
        path = newest(Path(__file__).resolve().parent.parent / "Master" / "Backups" / "Neon") or newest("Backups")
    if not path or not Path(path).is_file():
        print("No backup file found.", file=sys.stderr)
        return 2
    report, bad = verify(path)
    for name, (expected, actual) in sorted(report.items()):
        print(f"{name:40} {actual:>8} rows")
    print("OK: backup restores cleanly into a scratch database." if not bad else "PROBLEM tables: " + ", ".join(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
