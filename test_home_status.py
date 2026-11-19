"""Home status reports this account's leave-now choice and nothing else."""
import sqlite3
import unittest

import phone_push
from planner_api import _home_status


class HomeStatusTests(unittest.TestCase):
    def test_leave_alerts_follow_the_account_setting(self):
        connection = sqlite3.connect(':memory:')
        connection.row_factory = sqlite3.Row
        connection.execute('CREATE TABLE settings(setting_key TEXT PRIMARY KEY, setting_value TEXT)')
        self.assertFalse(_home_status(connection)['leave_alerts_enabled'])
        phone_push.save(connection, 'leave_alerts', {'enabled': True, 'window_minutes': 8})
        self.assertTrue(_home_status(connection)['leave_alerts_enabled'])
        connection.close()


if __name__ == '__main__':
    unittest.main()
