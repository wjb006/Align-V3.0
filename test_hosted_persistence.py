"""Local contract tests; optional real Postgres tests use only a loopback test DB."""
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import app
import postgres_support as pg
import render_start
import sqlite_support
from beta_support import BetaStore, BetaError


class AdapterTests(unittest.TestCase):
    def test_sqlite_default_and_closing_behavior(self):
        with patch.dict(os.environ, {'ALIGN_DATABASE_BACKEND': 'sqlite'}):
            with sqlite_support.connect(':memory:') as c:
                self.assertIsInstance(c, sqlite3.Connection)
                self.assertEqual(c.execute('PRAGMA foreign_keys').fetchone()[0], 1)
            with self.assertRaises(sqlite3.ProgrammingError):
                c.execute('SELECT 1')

    def test_routing_and_no_fallback(self):
        self.assertEqual(pg.schema_for('/srv/align.sqlite3'), 'align_owner')
        self.assertEqual(pg.schema_for('/srv/beta_users.sqlite3'), 'align_auth')
        for path in ('beta_data/user.sqlite3', 'beta_data/align.sqlite3', 'unknown.sqlite3', ':memory:'):
            with self.assertRaises(RuntimeError):
                pg.schema_for(path)
        with patch.dict(os.environ, {'ALIGN_DATABASE_BACKEND': 'postgres', 'DATABASE_URL': ''}), patch('sqlite_support.sqlite3.connect') as local:
            with self.assertRaises(RuntimeError):
                sqlite_support.connect('align.sqlite3')
            local.assert_not_called()
        with patch.dict(os.environ, {'ALIGN_DATABASE_BACKEND': 'postgre'}):
            with self.assertRaises(RuntimeError):
                sqlite_support.connect('align.sqlite3')

    def test_parameters_literals_comments_and_casefold(self):
        sql = "SELECT '?' AS quoted, '50%' AS percent, ? -- ?\n WHERE email=? COLLATE NOCASE"
        self.assertEqual(pg.translate(sql), "SELECT '?' AS quoted, '50%%' AS percent, %s -- ?\n WHERE LOWER(email)=LOWER(%s)")
        self.assertEqual(pg.translate('BEGIN IMMEDIATE'), 'BEGIN')

    def test_rows_are_named_positional_iterable_and_json_safe(self):
        row = pg.Row(('name', 'created'), ('Owner', datetime(2026, 9, 21, tzinfo=timezone.utc)))
        self.assertEqual(row[0], row['name'])
        self.assertEqual(dict(row)['created'], '2026-09-21T00:00:00+00:00')
        self.assertEqual(tuple(row)[0], 'Owner')

    def test_transaction_commits_rolls_back_and_closes(self):
        raw = MagicMock()
        with pg.Connection(raw, 'align_owner'):
            pass
        raw.commit.assert_called_once()
        raw.close.assert_called_once()
        raw.reset_mock()
        with self.assertRaises(ValueError), pg.Connection(raw, 'align_owner'):
            raise ValueError('test')
        raw.rollback.assert_called_once()
        raw.close.assert_called_once()

    def test_ddl_scripts_and_unknown_pragmas_fail(self):
        c = pg.Connection(MagicMock(), 'align_owner')
        for sql in ('CREATE TABLE example(id int)', 'PRAGMA foreign_keys=OFF', 'PRAGMA integrity_check'):
            with self.assertRaises(sqlite3.NotSupportedError):
                c.execute(sql)
        with self.assertRaises(sqlite3.NotSupportedError):
            c.executescript('SELECT 1; SELECT 2;')

    def test_insert_conflict_and_lastrowid(self):
        c = pg.Connection(MagicMock(), 'align_owner')
        c._identities['locations'] = 'id'
        with patch.object(c, '_run', return_value=pg.Result([pg.Row(('id',), (42,))], 1)) as run:
            result = c.execute('INSERT OR IGNORE INTO locations(name) VALUES(?)', ('x',))
            self.assertEqual(result.lastrowid, 42)
            self.assertEqual(result.rowcount, 1)
            self.assertIn('ON CONFLICT DO NOTHING RETURNING "id"', run.call_args.args[0])
        c._identities['beta_sessions'] = None
        with patch.object(c, '_run', return_value=pg.Result(rowcount=1)) as run:
            c.execute('INSERT OR REPLACE INTO beta_sessions(session_hash,user_id,expires) VALUES(?,?,?)', ('s', 'u', 1))
            self.assertIn('ON CONFLICT (session_hash) DO UPDATE SET user_id=EXCLUDED.user_id, expires=EXCLUDED.expires', run.call_args.args[0])

    def test_connection_diagnostics_never_echo_driver_credentials(self):
        secret = 'password=example-secret postgresql://user:another-secret@host/db'
        message = pg._safe_connection_error(pg.psycopg.OperationalError(secret), 'different-dsn')
        self.assertNotIn('example-secret', message)
        self.assertNotIn('another-secret', message)

    def test_driver_errors_do_not_disclose_connection_or_values(self):
        raw = MagicMock()
        raw.cursor.return_value.__enter__.return_value.execute.side_effect = pg.psycopg.OperationalError('secret-dsn')
        with self.assertRaises(sqlite3.OperationalError) as caught:
            pg.Connection(raw, 'align_auth').execute('SELECT ?', ('private',))
        self.assertNotIn('secret', str(caught.exception))


class StartupTests(unittest.TestCase):
    def store_with_owners(self, owners):
        store = MagicMock()
        c = store._connect.return_value.__enter__.return_value
        c.execute.return_value.fetchall.return_value = owners
        return store, c

    def test_existing_password_never_hashed_or_updated(self):
        store, c = self.store_with_owners([{'user_id': 'owner', 'password_hash': 'existing'}])
        render_start.bootstrap_hosted_owner(store, '')
        store.hash_password.assert_not_called()
        self.assertFalse(any(call.args[0].startswith('UPDATE') for call in c.execute.call_args_list))

    def test_empty_password_bootstraps_only_with_strong_password(self):
        store, c = self.store_with_owners([{'user_id': 'owner', 'password_hash': ''}])
        with self.assertRaises(RuntimeError):
            render_start.bootstrap_hosted_owner(store, '')
        render_start.bootstrap_hosted_owner(store, 'long enough bootstrap password')
        self.assertIn("COALESCE(password_hash,'')=''", c.execute.call_args.args[0])

    def test_duplicate_owners_stop_before_mutation(self):
        store, c = self.store_with_owners([{}, {}])
        with self.assertRaises(RuntimeError):
            render_start.bootstrap_hosted_owner(store, 'long enough bootstrap password')
        store.hash_password.assert_not_called()

    def test_hosted_init_skips_sqlite_migrations(self):
        with patch.dict(os.environ, {'ALIGN_DATABASE_BACKEND': 'postgres'}), patch('app.connect') as connect, patch('app.migration_runner.upgrade') as upgrade, patch('postgres_support.validate_v3_storage') as validate:
            app.initialise_database_at(Path('align.sqlite3'))
            app.db_connection()
            app.FixedDatabaseApp(Path('align.sqlite3')).db_connection()
            upgrade.assert_not_called()
            validate.assert_called_once()
            connect.return_value.__enter__.return_value.executescript.assert_not_called()

    def test_tester_routes_fail_clearly(self):
        store = BetaStore.__new__(BetaStore)
        store.owner_database = Path('align.sqlite3')
        with patch.dict(os.environ, {'ALIGN_DATABASE_BACKEND': 'postgres'}):
            with self.assertRaises(BetaError):
                store.database_for({'is_owner': 0, 'database_path': 'beta_data/user.sqlite3'})
            with self.assertRaises(BetaError):
                store._create_pending_user('test@example.com', '', None)

    def test_failed_probe_prevents_ready_message_and_server(self):
        with patch.dict(os.environ, {'ALIGN_DATABASE_BACKEND': 'postgres', 'ALIGN_HOSTING_MODE': 'disposable-preview'}), patch('app.initialise_database'), patch('postgres_support.prepare_calendar_locations'), patch('beta_support.BetaStore'), patch('render_start.bootstrap_hosted_owner'), patch('postgres_support.verify_hosted_storage', side_effect=RuntimeError('probe failed')), patch('app.AlignServer') as server, patch('builtins.print') as output, patch.object(app, 'BETA_STORE'), patch.object(app, 'DATABASE'), patch.object(app, 'BETA_MODE'):
            with self.assertRaises(RuntimeError):
                render_start.main()
            server.assert_not_called()
            output.assert_not_called()


@unittest.skipUnless(os.environ.get('ALIGN_TEST_POSTGRES_URL'), 'Set a loopback ALIGN_TEST_POSTGRES_URL for integration tests')
class PostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from urllib.parse import urlparse
        cls.dsn = os.environ['ALIGN_TEST_POSTGRES_URL']
        parsed = urlparse(cls.dsn)
        if parsed.hostname not in ('localhost', '127.0.0.1') or parsed.path != '/align_persistence_test':
            raise RuntimeError('Integration fixture requires a local align_persistence_test database')
        with pg.psycopg.connect(cls.dsn) as c:
            c.execute((Path(__file__).parent / 'tests' / 'hosted_schema_fixture.sql').read_text())

    def setUp(self):
        self.env = patch.dict(os.environ, {'ALIGN_DATABASE_BACKEND': 'postgres', 'DATABASE_URL': self.dsn,
                                           'ALIGN_HOSTING_MODE': 'persistent', 'ALIGN_PREVIEW_PASSWORD': 'IntegrationOnlyPassword123!'})
        self.env.start()
        self.addCleanup(self.env.stop)
        pg.prepare_calendar_locations()

    def test_schema_survives_commit_rollback_and_sql_boundaries(self):
        for path, schema, table in [('align.sqlite3', 'align_owner', 'personal_items'),
                                    ('beta_users.sqlite3', 'align_auth', 'beta_users')]:
            with sqlite_support.connect(path) as c:
                for boundary in (c.commit, c.rollback, lambda: c.execute('COMMIT'), lambda: c.execute('ROLLBACK')):
                    boundary()
                    self.assertEqual(c.execute('SELECT current_schema()').fetchone()[0], schema)
                    self.assertEqual(c.execute('SHOW timezone').fetchone()[0], 'UTC')
                    c.execute(f'SELECT COUNT(*) FROM {table}').fetchone()

    def test_owner_restart_inbox_and_adapter_contract(self):
        import transport_places
        import transport_service
        transport_service.prepare_hosted_storage()
        transport_service.prepare_hosted_storage()
        with sqlite_support.connect('align.sqlite3') as c:
            self.assertIsInstance(transport_places.items(c)['items'], list)
            self.assertEqual(transport_service.preferences(c)['arrival_buffer'], 10)
            source, _ = app.import_ics_calendar(c, 'Location test', 'BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:hosted-location-test\nDTSTART:20300702T120000\nDTEND:20300702T130000\nSUMMARY:Hosted journey test\nLOCATION:Liverpool Lime Street\nEND:VEVENT\nEND:VCALENDAR')
            imported = next(item for item in transport_places.items(c)['items'] if item['title'] == 'Hosted journey test')
            self.assertEqual(transport_service.event(c, imported['key'])[1], 'Liverpool Lime Street')
            c.execute('DELETE FROM calendar_sources WHERE id=?', (source,))
        with tempfile.TemporaryDirectory() as root:
            store = BetaStore(Path(root), Path('align.sqlite3'), app.initialise_database_at)
            render_start.bootstrap_hosted_owner(store, os.environ['ALIGN_PREVIEW_PASSWORD'])
            before = dict(store.owner())
            render_start.bootstrap_hosted_owner(store, 'a completely different password!')
            after = dict(store.owner())
            for key in ('user_id', 'created_at', 'password_hash', 'password_set_at'):
                self.assertEqual(before[key], after[key])
            self.assertTrue(store.verify_password(after['password_hash'], os.environ['ALIGN_PREVIEW_PASSWORD']))
            signed_in, token = store.login('preview@example.com', os.environ['ALIGN_PREVIEW_PASSWORD'])
            self.assertEqual(signed_in['user_id'], before['user_id'])
            self.assertEqual(store.by_session(token)['user_id'], before['user_id'])
            self.assertEqual(store.user_by_email('PREVIEW@EXAMPLE.COM')['user_id'], before['user_id'])
            with store._connect() as c:
                for expires in (10, 20):
                    c.execute('INSERT OR REPLACE INTO beta_sessions(session_hash,user_id,expires) VALUES(?,?,?)', ('test-session', before['user_id'], expires))
                self.assertEqual(c.execute('SELECT expires FROM beta_sessions WHERE session_hash=?', ('test-session',)).fetchone()[0], 20)
            with sqlite_support.connect('align.sqlite3') as c:
                self.assertEqual(app.personal_planner.bootstrap(c)['items'], [])
                self.assertEqual(app.dashboard(c)['summary']['shift_count'], 0)
                self.assertEqual(app.master_data(c)['templates'], [])
                c.execute('INSERT OR IGNORE INTO personal_items(id,kind,title) VALUES(?,?,?)', ('persistence-test', 'note', 'Test 50% ?'))
                self.assertEqual(c.execute('INSERT OR IGNORE INTO personal_items(id,kind,title) VALUES(?,?,?)', ('persistence-test', 'note', 'duplicate')).rowcount, 0)
                ident = c.execute('INSERT INTO locations(name,address) VALUES(?,?)', ('Test location', '')).lastrowid
                self.assertIsInstance(ident, int)
            with patch.object(app, 'BETA_STORE'), patch.object(app, 'DATABASE'), patch.object(app, 'BETA_MODE'):
                render_start.prepare_preview()
                render_start.prepare_preview()
                self.assertTrue(app.health_status()['database']['available'])
            with sqlite_support.connect('align.sqlite3') as c:
                self.assertEqual(c.execute('SELECT title FROM personal_items WHERE id=?', ('persistence-test',)).fetchone()[0], 'Test 50% ?')
                c.execute('DELETE FROM personal_items WHERE id=?', ('persistence-test',))
                c.execute('DELETE FROM locations WHERE id=?', (ident,))
            with sqlite_support.connect('align.sqlite3') as c:
                self.assertIsNone(c.execute('SELECT id FROM personal_items WHERE id=?', ('persistence-test',)).fetchone())
            with self.assertRaises(ValueError), sqlite_support.connect('align.sqlite3') as c:
                c.execute('INSERT INTO personal_items(id,kind,title) VALUES(?,?,?)', ('rollback', 'note', 'discard'))
                raise ValueError('roll back')
            with sqlite_support.connect('align.sqlite3') as c:
                self.assertIsNone(c.execute('SELECT id FROM personal_items WHERE id=?', ('rollback',)).fetchone())
            # Existing account with no password: retain identity/creation time.
            with store._connect() as c:
                c.execute("UPDATE beta_users SET password_hash='',password_set_at='' WHERE user_id=?", (before['user_id'],))
            render_start.bootstrap_hosted_owner(store, 'AnotherBootstrapPassword456!')
            bootstrapped = dict(store.owner())
            self.assertEqual(bootstrapped['created_at'], before['created_at'])
            self.assertTrue(bootstrapped['password_set_at'])
            self.assertTrue(store.verify_password(bootstrapped['password_hash'], 'AnotherBootstrapPassword456!'))


if __name__ == '__main__':
    unittest.main()
