"""Two invited people do not share a planner database."""
import tempfile
import unittest
from pathlib import Path

from beta_support import BetaStore
from sqlite_support import connect


def initialise(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as connection:
        connection.execute('CREATE TABLE IF NOT EXISTS settings(setting_key TEXT PRIMARY KEY, setting_value TEXT)')


class TesterIsolationTests(unittest.TestCase):
    def test_each_invite_has_its_own_database(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            store = BetaStore(root, root / 'align.sqlite3', initialise)
            owner, _code = store.ensure_owner('owner@example.com')
            first = store.create_invite('one@example.com', 'One', initialise, owner['user_id'], 'iso-1')[0]
            second = store.create_invite('two@example.com', 'Two', initialise, owner['user_id'], 'iso-2')[0]
            person_a, _token = store.complete_invite('one@example.com', first['invite_code'], 'CoffeeRugby2026')
            person_b, _token = store.complete_invite('two@example.com', second['invite_code'], 'CoffeeRugby2026')
            path_a = store.database_for(person_a)
            path_b = store.database_for(person_b)
            self.assertNotEqual(path_a, path_b)
            self.assertNotEqual(path_a, store.database_for(owner))
            with connect(path_a) as connection:
                connection.execute("INSERT INTO settings VALUES('private_note','only-a')")
            with connect(path_b) as connection:
                self.assertIsNone(connection.execute("SELECT setting_value FROM settings WHERE setting_key='private_note'").fetchone())


if __name__ == '__main__':
    unittest.main()
