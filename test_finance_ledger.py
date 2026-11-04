"""Finance ledger kept in finance.db beside the planner database."""
import sqlite3
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import app
import finance_db
from test_support import IsolatedAppServer

ZONE = ZoneInfo('Europe/London')


class FinanceLedgerTests(IsolatedAppServer, unittest.TestCase):
    def test_fresh_file_is_created_beside_the_planner_database(self):
        sidecar = Path(app.DATABASE).parent / 'finance.db'
        self.assertFalse(sidecar.exists())
        week = self.json_request('GET', '/api/week')
        self.assertFalse(sidecar.exists())
        self.assertTrue(week['finance_calendar']['visible'])
        self.assertEqual(week['finance_events'], [])
        created = self.json_request('POST', '/api/finance/entries', {
            'entry_kind': 'transaction', 'direction': 'in', 'amount': '120.50',
            'booked_on': date.today().isoformat(), 'category': 'Wages', 'payee': 'Clinic',
        })
        self.assertTrue(sidecar.exists())
        self.assertEqual(created['entry']['amount_pence'], 12050)
        summary = self.json_request('GET', '/api/finance')
        self.assertEqual(summary['balance_pence'], 12050)
        self.assertEqual(summary['month']['in_pence'], 12050)

    def test_card_numbers_and_passwords_are_refused(self):
        status, _, body = self.request('POST', '/api/finance/entries', {
            'entry_kind': 'transaction', 'direction': 'out', 'amount': '10.00',
            'booked_on': date.today().isoformat(), 'notes': 'card 4111111111111111',
        })
        self.assertEqual(status, 400)
        self.assertNotIn(b'4111111111111111', body)
        status, _, body = self.request('POST', '/api/finance/entries', {
            'entry_kind': 'transaction', 'direction': 'out', 'amount': '10.00',
            'booked_on': date.today().isoformat(), 'account_note': 'password hunter2',
        })
        self.assertEqual(status, 400)
        self.assertNotIn(b'hunter2', body)
        self.assertEqual(self.json_request('GET', '/api/finance')['entries'], [])

    def test_bills_income_balance_and_payment_link(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        bill = self.json_request('POST', '/api/finance/entries', {
            'entry_kind': 'bill', 'amount': '40.00', 'booked_on': yesterday,
            'category': 'Energy', 'payee': 'Supplier',
        })['entry']
        income = self.json_request('POST', '/api/finance/entries', {
            'entry_kind': 'expected_income', 'amount': '80.00', 'booked_on': yesterday, 'payee': 'Wages',
        })['entry']
        summary = self.json_request('GET', '/api/finance')
        self.assertEqual(summary['balance_pence'], 0)
        codes = {item['code'] for item in summary['reminders']}
        self.assertIn('overdue_bill', codes)
        self.assertIn('income_missing', codes)
        self.json_request('POST', '/api/finance/entries', {
            'entry_kind': 'transaction', 'direction': 'out', 'amount': '40.00',
            'booked_on': date.today().isoformat(), 'payee': 'Supplier', 'bill_id': bill['id'],
        })
        paid = self.json_request('GET', '/api/finance')
        self.assertEqual(paid['balance_pence'], -4000)
        self.assertNotIn('overdue_bill', {item['code'] for item in paid['reminders']})
        self.assertIn('income_missing', {item['code'] for item in paid['reminders']})
        self.assertEqual(income['entry_kind'], 'expected_income')

    def test_low_balance_and_csv_and_hidden_calendar(self):
        self.json_request('PATCH', '/api/finance/settings', {'low_balance': '50.00', 'reminder_days': 3})
        imported = self.json_request('POST', '/api/finance/import', {'csv': (
            'date,amount,direction,category,payee,account,notes\n'
            f'{date.today().isoformat()},25.00,out,Food,Shop,Current,\n'
            f'{date.today().isoformat()},-5.00,,Travel,Bus,,\n'
        )})
        self.assertEqual(len(imported['created']), 2)
        summary = imported['summary']
        self.assertEqual(summary['balance_pence'], -3000)
        self.assertTrue(any(item['code'] == 'low_balance' for item in summary['reminders']))
        self.assertTrue(any(item['category'] == 'Food' for item in summary['categories']))
        week = self.json_request('GET', '/api/week')
        self.assertTrue(week['finance_events'])
        self.json_request('PATCH', '/api/finance/settings', {'calendar_visible': False})
        hidden = self.json_request('GET', '/api/week')
        self.assertFalse(hidden['finance_calendar']['visible'])
        self.assertEqual(hidden['finance_events'], [])
        self.assertEqual(len(self.json_request('GET', '/api/finance')['entries']), 2)

    def test_a_second_database_does_not_see_the_first_ledger(self):
        self.json_request('POST', '/api/finance/entries', {
            'entry_kind': 'transaction', 'direction': 'in', 'amount': '10.00',
            'booked_on': date.today().isoformat(), 'payee': 'Mine',
        })
        other = Path(self.temp.name) / 'other' / 'align.sqlite3'
        other.parent.mkdir()
        sqlite3.connect(other).close()
        with finance_db.connect(other) as connection:
            self.assertEqual(finance_db.summary(connection)['entries'], [])
        self.assertEqual(self.json_request('GET', '/api/finance')['balance_pence'], 1000)

    def test_postgres_connections_do_not_open_a_sidecar(self):
        class Remote:
            def execute(self, *_args, **_kwargs):
                raise RuntimeError('no local file')

        self.assertEqual(
            finance_db.planner_slice(Remote(), date.today(), date.today()),
            {'visible': True, 'events': []},
        )

    def test_push_reminder_uses_a_stable_id_without_the_note(self):
        today = datetime.now(ZONE).date().isoformat()
        self.json_request('POST', '/api/finance/entries', {
            'entry_kind': 'bill', 'amount': '12.00', 'booked_on': today,
            'payee': 'Rent', 'notes': 'private account note',
        })
        moment = datetime.now(ZONE).replace(hour=10, minute=0, second=0, microsecond=0)
        with app.db_connection() as connection:
            found = finance_db.push_reminders(connection, moment.astimezone(timezone.utc))
        self.assertTrue(found)
        event_id, due = found[0]
        self.assertTrue(event_id.startswith('finance:due_soon:'))
        self.assertNotIn('private', event_id)
        self.assertEqual(due.tzinfo, timezone.utc)


if __name__ == '__main__':
    unittest.main()
