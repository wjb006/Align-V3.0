from datetime import datetime, timezone
import sqlite3
import tempfile
import unittest
from pathlib import Path

from migration_runner import migrate, rollback, upgrade
from transport_ranking import rank

class Build149TransportTests(unittest.TestCase):
    def test_arrive_by_ranking_rejects_cancelled_and_late(self):
        routes=[
            {'legs':[{'mode':'rail','start':'2026-09-07T07:00:00+00:00','end':'2026-09-07T07:45:00+00:00'}],'disruption':'cancelled'},
            {'legs':[{'mode':'bus','start':'2026-09-07T07:02:00+00:00','end':'2026-09-07T07:48:00+00:00'}],'live':False},
            {'legs':[{'mode':'bus','start':'2026-09-07T07:02:00+00:00','end':'2026-09-07T08:02:00+00:00'}],'live':False},
        ]
        result=rank(routes,'2026-09-07T07:50:00+00:00',['bus','rail','walk'], now=datetime(2026,9,7,6,tzinfo=timezone.utc))
        self.assertEqual(result['state'],'on_time'); self.assertEqual(result['journeys'][0]['badges'][0],'Recommended')

    def test_migration_and_rollback_preserve_existing_data(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/'align.sqlite3'; c=sqlite3.connect(db); c.execute('CREATE TABLE keep(value TEXT)'); c.execute("INSERT INTO keep VALUES ('safe')"); c.commit(); c.close()
            self.assertEqual(migrate(db)['status'],'applied'); self.assertEqual(migrate(db)['status'],'skipped'); self.assertEqual(rollback(db)['status'],'rolled_back')
            c=sqlite3.connect(db); self.assertEqual(c.execute('SELECT value FROM keep').fetchone()[0],'safe'); self.assertIsNone(c.execute("SELECT name FROM sqlite_master WHERE name='assets'").fetchone()); c.close()

    def test_legacy_transport_cache_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/'align.sqlite3'
            c=sqlite3.connect(db)
            c.execute('CREATE TABLE transport_cache (cache_key TEXT PRIMARY KEY, user_key TEXT NOT NULL, payload TEXT NOT NULL, provider TEXT NOT NULL, fetched_at TEXT NOT NULL, expires_at TEXT NOT NULL, etag TEXT NOT NULL)')
            c.execute("INSERT INTO transport_cache VALUES ('old','account','payload','legacy','2026-01-01','2026-01-02','')")
            c.commit(); c.close()
            self.assertEqual(upgrade(db)['status'],'applied')
            c=sqlite3.connect(db)
            self.assertEqual(c.execute("SELECT payload FROM transport_cache WHERE cache_key='old'").fetchone()[0],'payload')
            self.assertIsNotNone(c.execute("SELECT name FROM sqlite_master WHERE name='transport_journey_cache'").fetchone())
            self.assertIsNotNone(c.execute("SELECT name FROM sqlite_master WHERE name='transport_preferences'").fetchone())
            c.close()

if __name__=='__main__': unittest.main()
