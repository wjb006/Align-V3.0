import sqlite3, tempfile, unittest
from pathlib import Path
from migration_runner import migrate as run_asset_studio_migration, rollback as rollback_asset_studio

ROOT = Path(__file__).resolve().parent

class AssetStudioMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.db = Path(self.tmp.name) / 'align.sqlite3'; c=sqlite3.connect(self.db); c.execute('CREATE TABLE existing_data(value TEXT)'); c.commit(); c.close()
    def tearDown(self): self.tmp.cleanup()
    def test_first_run_and_second_skip(self):
        first = run_asset_studio_migration(self.db, ROOT/'migrations'); self.assertEqual(first['status'], 'applied')
        second = run_asset_studio_migration(self.db, ROOT/'migrations'); self.assertEqual(second['status'], 'skipped')
        c=sqlite3.connect(self.db); self.assertEqual(c.execute("SELECT COUNT(*) FROM asset_categories WHERE category_group='workplace' AND built_in=1").fetchone()[0],12); self.assertEqual(c.execute("SELECT COUNT(*) FROM asset_categories WHERE category_group='event_type' AND built_in=1").fetchone()[0],26); self.assertEqual(c.execute("SELECT COUNT(*) FROM asset_categories WHERE category_group='place' AND built_in=1").fetchone()[0],6); self.assertEqual(c.execute("SELECT COUNT(*) FROM asset_categories WHERE category_group='travel' AND built_in=1").fetchone()[0],6); c.close()
    def test_rollback_and_existing_data(self):
        c=sqlite3.connect(self.db); c.execute("INSERT INTO existing_data VALUES('keep')"); c.commit(); c.close(); run_asset_studio_migration(self.db, ROOT/'migrations'); rollback_asset_studio(self.db, ROOT/'migrations'); c=sqlite3.connect(self.db); self.assertEqual(c.execute("SELECT value FROM existing_data").fetchone()[0],'keep'); self.assertIsNone(c.execute("SELECT name FROM sqlite_master WHERE name='assets'").fetchone()); c.close()
    def test_failed_migration_leaves_no_marker(self):
        bad = Path(self.tmp.name)/'bad'; bad.mkdir(); (bad/'149_asset_studio.sql').write_text('CREATE TABLE broken(x); SELECT no_such_function();', encoding='utf-8');
        with self.assertRaises(sqlite3.Error): run_asset_studio_migration(self.db,bad)
        c=sqlite3.connect(self.db)
        tables={row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertNotIn('broken', tables)
        if 'schema_migrations' in tables:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM schema_migrations WHERE migration_id='149_asset_studio'").fetchone()[0],0)
        self.assertIn('existing_data', tables)
        c.close()

if __name__ == '__main__': unittest.main()
