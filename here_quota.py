"""Conservative shared transit allowance, reserved before each upstream call.

This limits Align only; other applications using the HERE account consume the
same provider allowance. Failed upstream calls remain counted intentionally.
"""
from datetime import datetime, timezone
from pathlib import Path
from sqlite_support import connect, postgres_enabled

LIMIT = 1000
WINDOW_SECONDS = 32 * 24 * 60 * 60


def reserve():
    if not postgres_enabled():
        raise ValueError('Hosted HERE transit requires persistent usage accounting.')
    try:
        with connect(Path('beta_users.sqlite3')) as c:
            # Serialize creation, counting and reservations across all workers.
            c.execute('SELECT pg_advisory_xact_lock(151202625)')
            # PostgreSQL-specific DDL; the SQLite compatibility API rejects DDL.
            c.raw.execute('''CREATE TABLE IF NOT EXISTS align_here_transit_usage (
                requested_at BIGINT NOT NULL
            )''')
            now = int(datetime.now(timezone.utc).timestamp())
            c.execute('DELETE FROM align_here_transit_usage WHERE requested_at<?',
                      (now - WINDOW_SECONDS,))
            count = c.execute('SELECT COUNT(*) FROM align_here_transit_usage').fetchone()[0]
            if count >= LIMIT:
                raise ValueError('Align has reached its free transit request limit. Enter travel details manually until the allowance becomes available.')
            c.execute('INSERT INTO align_here_transit_usage(requested_at) VALUES(?)', (now,))
    except ValueError:
        raise
    except Exception:
        raise ValueError('Transit usage accounting is unavailable. No HERE request was sent.') from None
