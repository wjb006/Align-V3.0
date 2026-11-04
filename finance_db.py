"""Separate finance ledger stored beside the planner database.

The file is finance.db in the same folder as the main database
(%LOCALAPPDATA%\\Align on Windows). It is created empty and migrated on
first use. Card numbers and passwords are refused and never written.
"""
from __future__ import annotations

import csv
import io
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

DATABASE_NAME = 'finance.db'
ZONE = ZoneInfo('Europe/London')
MAX_CSV_CHARS = 200_000
MAX_CSV_ROWS = 400
_CARD = re.compile(r'\d[\d\s-]{11,22}\d')
_SECRET = re.compile(r'(?i)\b(password|passwd|passcode|secret|cvv|cvc)\b')
_AMOUNT = re.compile(r'-?\d+(?:\.\d{1,2})?')
_DATE = re.compile(r'\d{4}-\d{2}-\d{2}')


class FinanceError(Exception):
    def __init__(self, message, code='invalid', status=400):
        super().__init__(message)
        self.code = code
        self.status = status


def sidecar_for_connection(connection):
    """Return the finance.db path for a SQLite planner connection, if it has a file."""
    try:
        row = connection.execute('PRAGMA database_list').fetchone()
    except Exception:
        return None
    if row is None:
        return None
    file_name = row['file'] if hasattr(row, 'keys') else row[2]
    if not file_name:
        return None
    return Path(file_name).parent / DATABASE_NAME


def connect(main_database: Path) -> sqlite3.Connection:
    path = Path(main_database).parent / DATABASE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    _migrate(connection)
    return connection


def _migrate(connection):
    connection.executescript(
        '''
        CREATE TABLE IF NOT EXISTS finance_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            calendar_visible INTEGER NOT NULL DEFAULT 1 CHECK (calendar_visible IN (0, 1)),
            low_balance_pence INTEGER NOT NULL DEFAULT 0,
            reminder_days INTEGER NOT NULL DEFAULT 3 CHECK (reminder_days BETWEEN 0 AND 60)
        );
        INSERT OR IGNORE INTO finance_settings(id) VALUES (1);
        CREATE TABLE IF NOT EXISTS finance_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_kind TEXT NOT NULL CHECK (entry_kind IN ('transaction','bill','expected_income')),
            direction TEXT NOT NULL CHECK (direction IN ('in','out')),
            amount_pence INTEGER NOT NULL CHECK (amount_pence > 0 AND amount_pence <= 10000000000),
            booked_on TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT '',
            payee TEXT NOT NULL DEFAULT '',
            account_note TEXT NOT NULL DEFAULT '',
            recurring INTEGER NOT NULL DEFAULT 0 CHECK (recurring IN (0, 1)),
            notes TEXT NOT NULL DEFAULT '',
            bill_id INTEGER REFERENCES finance_entries(id) ON DELETE SET NULL,
            income_id INTEGER REFERENCES finance_entries(id) ON DELETE SET NULL,
            received INTEGER NOT NULL DEFAULT 0 CHECK (received IN (0, 1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_finance_entries_date ON finance_entries(booked_on, entry_kind);
        '''
    )
    connection.commit()


def _now():
    return datetime.now().replace(microsecond=0).isoformat(timespec='seconds')


def assert_safe(*parts):
    blob = '\n'.join(str(part or '') for part in parts)
    if _SECRET.search(blob):
        raise FinanceError('Passwords and card security codes are not stored.', 'sensitive_data')
    for run in _CARD.findall(blob):
        digits = re.sub(r'\D', '', run)
        if 13 <= len(digits) <= 19:
            raise FinanceError('Card numbers are not stored.', 'sensitive_data')


def parse_pence(value, allow_sign=False):
    text = str(value or '').strip().replace('£', '').replace(',', '')
    if not _AMOUNT.fullmatch(text):
        raise FinanceError('Enter an amount in pounds and pence.', 'invalid_amount')
    negative = text.startswith('-')
    if negative and not allow_sign:
        raise FinanceError('Enter an amount in pounds and pence.', 'invalid_amount')
    whole, _, fraction = text.lstrip('-').partition('.')
    pence = int(whole) * 100 + int((fraction + '00')[:2])
    if pence <= 0 or pence > 10_000_000_000:
        raise FinanceError('Enter an amount in pounds and pence.', 'invalid_amount')
    return pence, negative


def _clean(value, limit):
    return str(value or '').strip()[:limit]


def _iso_date(value):
    text = str(value or '').strip()
    if not _DATE.fullmatch(text):
        raise FinanceError('Use a date as YYYY-MM-DD.', 'invalid_date')
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as error:
        raise FinanceError('Use a date as YYYY-MM-DD.', 'invalid_date') from error


def _settings(connection):
    row = connection.execute('SELECT * FROM finance_settings WHERE id=1').fetchone()
    return {
        'calendar_visible': bool(row['calendar_visible']),
        'low_balance_pence': int(row['low_balance_pence']),
        'reminder_days': int(row['reminder_days']),
    }


def _public(row):
    item = dict(row)
    return {
        'id': item['id'],
        'entry_kind': item['entry_kind'],
        'direction': item['direction'],
        'amount_pence': item['amount_pence'],
        'booked_on': item['booked_on'],
        'category': item['category'],
        'payee': item['payee'],
        'account_note': item['account_note'],
        'recurring': bool(item['recurring']),
        'notes': item['notes'],
        'bill_id': item['bill_id'],
        'income_id': item['income_id'],
        'received': bool(item['received']),
    }


def _rows(connection):
    return connection.execute('SELECT * FROM finance_entries ORDER BY booked_on, id').fetchall()


def add_entry(connection, payload, commit=True):
    kind = str((payload or {}).get('entry_kind') or 'transaction')
    if kind not in {'transaction', 'bill', 'expected_income'}:
        raise FinanceError('Choose money in, money out, a bill, or expected income.', 'invalid_kind')
    direction = str(payload.get('direction') or '')
    if kind == 'bill':
        direction = 'out'
    elif kind == 'expected_income':
        direction = 'in'
    elif direction not in {'in', 'out'}:
        raise FinanceError('Choose whether this money comes in or goes out.', 'invalid_direction')
    if isinstance(payload.get('amount_pence'), int) and payload.get('amount') is None:
        amount = int(payload['amount_pence'])
        if amount <= 0 or amount > 10_000_000_000:
            raise FinanceError('Enter an amount in pounds and pence.', 'invalid_amount')
    else:
        amount, _negative = parse_pence(payload.get('amount'))
    booked = _iso_date(payload.get('booked_on'))
    category = _clean(payload.get('category'), 40)
    payee = _clean(payload.get('payee'), 80)
    account_note = _clean(payload.get('account_note'), 80)
    notes = _clean(payload.get('notes'), 200)
    assert_safe(category, payee, account_note, notes)
    recurring = 1 if payload.get('recurring') in (True, 1, '1', 'true', 'on') else 0
    bill_id = payload.get('bill_id') or None
    income_id = payload.get('income_id') or None
    if kind != 'transaction':
        bill_id = None
        income_id = None
    if bill_id is not None:
        bill = connection.execute("SELECT id FROM finance_entries WHERE id=? AND entry_kind='bill'", (int(bill_id),)).fetchone()
        if not bill:
            raise FinanceError('That bill could not be found.', 'bill_not_found', 404)
        bill_id = int(bill_id)
    else:
        bill_id = None
    if income_id is not None:
        income = connection.execute("SELECT id FROM finance_entries WHERE id=? AND entry_kind='expected_income'", (int(income_id),)).fetchone()
        if not income:
            raise FinanceError('That expected income could not be found.', 'income_not_found', 404)
        income_id = int(income_id)
    else:
        income_id = None
    stamp = _now()
    cursor = connection.execute(
        '''INSERT INTO finance_entries(entry_kind,direction,amount_pence,booked_on,category,payee,account_note,
           recurring,notes,bill_id,income_id,received,created_at,updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,0,?,?)''',
        (kind, direction, amount, booked, category, payee, account_note, recurring, notes, bill_id, income_id, stamp, stamp),
    )
    if income_id and direction == 'in':
        connection.execute('UPDATE finance_entries SET received=1, updated_at=? WHERE id=?', (stamp, income_id))
    if commit:
        connection.commit()
    return _public(connection.execute('SELECT * FROM finance_entries WHERE id=?', (cursor.lastrowid,)).fetchone())


def update_settings(connection, payload):
    current = _settings(connection)
    visible = current['calendar_visible'] if 'calendar_visible' not in payload else bool(payload.get('calendar_visible'))
    low = current['low_balance_pence']
    if 'low_balance' in payload:
        text = str(payload.get('low_balance') or '0').strip().replace('£', '').replace(',', '')
        low = 0 if text in {'0', '0.0', '0.00'} else parse_pence(text)[0]
    elif 'low_balance_pence' in payload:
        low = int(payload.get('low_balance_pence') or 0)
    days = current['reminder_days'] if 'reminder_days' not in payload else int(payload.get('reminder_days'))
    if not 0 <= days <= 60 or low < 0:
        raise FinanceError('Check the reminder settings and try again.', 'invalid_settings')
    connection.execute(
        'UPDATE finance_settings SET calendar_visible=?, low_balance_pence=?, reminder_days=? WHERE id=1',
        (1 if visible else 0, low, days),
    )
    connection.commit()
    return _settings(connection)


def delete_entry(connection, entry_id):
    cursor = connection.execute('DELETE FROM finance_entries WHERE id=?', (int(entry_id),))
    connection.commit()
    if cursor.rowcount == 0:
        raise FinanceError('That finance entry could not be found.', 'not_found', 404)


def _paid_bill_ids(rows):
    return {row['bill_id'] for row in rows if row['bill_id']}


def _received_income_ids(rows):
    linked = {row['income_id'] for row in rows if row['income_id']}
    return linked | {row['id'] for row in rows if row['entry_kind'] == 'expected_income' and row['received']}


def balance_pence(rows):
    total = 0
    for row in rows:
        if row['entry_kind'] != 'transaction':
            continue
        total += row['amount_pence'] if row['direction'] == 'in' else -row['amount_pence']
    return total


def _month_totals(rows, today):
    prefix = today.strftime('%Y-%m')
    incoming = outgoing = 0
    for row in rows:
        if row['entry_kind'] != 'transaction' or not str(row['booked_on']).startswith(prefix):
            continue
        if row['direction'] == 'in':
            incoming += row['amount_pence']
        else:
            outgoing += row['amount_pence']
    return incoming, outgoing


def _categories(rows, today):
    prefix = today.strftime('%Y-%m')
    totals = {}
    for row in rows:
        if row['entry_kind'] != 'transaction' or not str(row['booked_on']).startswith(prefix):
            continue
        key = (row['category'] or 'Uncategorised', row['direction'])
        totals[key] = totals.get(key, 0) + row['amount_pence']
    return [
        {'category': name, 'direction': direction, 'total_pence': amount}
        for (name, direction), amount in sorted(totals.items())
    ]


def _next_month(day):
    year = day.year + (1 if day.month == 12 else 0)
    month = 1 if day.month == 12 else day.month + 1
    last = (date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1) - timedelta(days=1)).day
    return date(year, month, min(day.day, last))


def cash_flow(rows, today, days=60):
    window_end = today + timedelta(days=days)
    paid = _paid_bill_ids(rows)
    received = _received_income_ids(rows)
    items = []
    for row in rows:
        when = date.fromisoformat(row['booked_on'])
        outstanding = (
            (row['entry_kind'] == 'bill' and row['id'] not in paid)
            or (row['entry_kind'] == 'expected_income' and row['id'] not in received)
        )
        if outstanding and when < today:
            when = today
        include = today <= when <= window_end
        if row['recurring'] and date.fromisoformat(row['booked_on']) < today and not (outstanding and row['entry_kind'] == 'bill'):
            upcoming = when
            while upcoming < today:
                upcoming = _next_month(upcoming)
            when = upcoming
            include = when <= window_end
        if not include:
            continue
        if row['entry_kind'] == 'bill' and row['id'] in paid:
            continue
        if row['entry_kind'] == 'expected_income' and row['id'] in received:
            continue
        label = row['payee'] or row['category'] or row['entry_kind'].replace('_', ' ')
        items.append({
            'date': when.isoformat(),
            'entry_id': row['id'],
            'entry_kind': row['entry_kind'],
            'direction': row['direction'],
            'amount_pence': row['amount_pence'],
            'label': label,
        })
    return sorted(items, key=lambda item: (item['date'], item['entry_id']))


def reminders(rows, today, settings):
    paid = _paid_bill_ids(rows)
    received = _received_income_ids(rows)
    lead = today + timedelta(days=settings['reminder_days'])
    found = []
    for row in rows:
        when = date.fromisoformat(row['booked_on'])
        if row['entry_kind'] == 'bill' and row['id'] not in paid:
            if when < today:
                found.append(_reminder('overdue_bill', row, 'This bill is overdue.'))
            elif when <= lead:
                found.append(_reminder('due_soon', row, 'This bill is due soon.'))
        if row['entry_kind'] == 'expected_income' and row['id'] not in received and when <= today:
            found.append(_reminder('income_missing', row, 'Expected income has not been recorded.'))
    projected = balance_pence(rows)
    for item in cash_flow(rows, today, 30):
        projected += item['amount_pence'] if item['direction'] == 'in' else -item['amount_pence']
    if projected < settings['low_balance_pence']:
        found.append({
            'code': 'low_balance',
            'entry_id': None,
            'booked_on': today.isoformat(),
            'message': 'The projected balance is below zero.' if settings['low_balance_pence'] == 0 else 'The projected balance is below the amount you asked to be warned about.',
            'amount_pence': projected,
        })
    return found


def _reminder(code, row, message):
    return {
        'code': code,
        'entry_id': row['id'],
        'booked_on': row['booked_on'],
        'message': message,
        'amount_pence': row['amount_pence'],
        'payee': row['payee'],
        'category': row['category'],
    }


def summary(connection, today=None):
    today = today or date.today()
    rows = _rows(connection)
    settings = _settings(connection)
    incoming, outgoing = _month_totals(rows, today)
    return {
        'balance_pence': balance_pence(rows),
        'month': {'in_pence': incoming, 'out_pence': outgoing, 'month': today.strftime('%Y-%m')},
        'categories': _categories(rows, today),
        'cash_flow': cash_flow(rows, today),
        'reminders': reminders(rows, today, settings),
        'entries': [_public(row) for row in rows],
        'settings': settings,
    }


def events_between(connection, start: date, end: date):
    settings = _settings(connection)
    if not settings['calendar_visible']:
        return []
    events = []
    for item in cash_flow(_rows(connection), start, (end - start).days):
        when = date.fromisoformat(item['date'])
        if when < start or when > end:
            continue
        title = f"{item['label']} · £{item['amount_pence'] / 100:.2f}"
        events.append({
            'id': item['entry_id'],
            'title': title,
            'start_at': f"{item['date']}T00:00",
            'end_at': f"{item['date']}T23:59",
            'all_day': 1,
            'origin': 'Finance',
            'category_name': 'Finance',
            'section_colour': '#0f766e',
            'notes': '',
            'location': '',
        })
    return events


def planner_slice(connection, start: date, end: date):
    path = sidecar_for_connection(connection)
    if path is None or not path.exists():
        return {'visible': True, 'events': []}
    finance = sqlite3.connect(path)
    finance.row_factory = sqlite3.Row
    try:
        _migrate(finance)
        visible = _settings(finance)['calendar_visible']
        return {'visible': visible, 'events': events_between(finance, start, end) if visible else []}
    finally:
        finance.close()


def import_csv(connection, text):
    if not isinstance(text, str) or len(text) > MAX_CSV_CHARS:
        raise FinanceError('That statement is too large to import.', 'csv_too_large', 413)
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise FinanceError('The statement needs a header row.', 'invalid_csv')
    fields = {name.strip().lower(): name for name in reader.fieldnames if name}
    payloads = []
    for index, raw in enumerate(reader, start=2):
        if len(payloads) >= MAX_CSV_ROWS:
            raise FinanceError('Import up to 400 rows at a time.', 'csv_too_large', 413)
        if not any(str(value or '').strip() for value in raw.values()):
            continue
        payloads.append(_csv_payload(raw, fields))
    created = []
    try:
        for payload in payloads:
            created.append(add_entry(connection, payload, commit=False))
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return created


def _cell(raw, fields, *names):
    for name in names:
        source = fields.get(name)
        if source and str(raw.get(source) or '').strip():
            return str(raw.get(source)).strip()
    return ''


def _csv_payload(raw, fields):
    amount_text = _cell(raw, fields, 'amount', 'value')
    pence, negative = parse_pence(amount_text, allow_sign=True)
    direction = _cell(raw, fields, 'direction', 'type').lower()
    if direction in {'in', 'income', 'credit'}:
        direction = 'in'
    elif direction in {'out', 'expense', 'debit', 'bill'}:
        direction = 'out'
    elif negative:
        direction = 'out'
    else:
        direction = 'in'
    kind = 'bill' if direction == 'out' and _cell(raw, fields, 'kind', 'entry_kind').lower() == 'bill' else 'transaction'
    if _cell(raw, fields, 'kind', 'entry_kind').lower() in {'expected_income', 'income expected'}:
        kind = 'expected_income'
        direction = 'in'
    return {
        'entry_kind': kind,
        'direction': direction,
        'amount_pence': pence,
        'booked_on': _cell(raw, fields, 'date', 'booked_on'),
        'category': _cell(raw, fields, 'category'),
        'payee': _cell(raw, fields, 'payee', 'source', 'description'),
        'account_note': _cell(raw, fields, 'account', 'account_note'),
        'notes': _cell(raw, fields, 'notes', 'note'),
        'recurring': _cell(raw, fields, 'recurring').lower() in {'1', 'true', 'yes'},
    }


def push_reminders(connection, now):
    """Return (event id, utc time) for finance reminders whose 09:00 London time is due."""
    path = sidecar_for_connection(connection)
    if path is None or not path.exists():
        return []
    finance = sqlite3.connect(path)
    finance.row_factory = sqlite3.Row
    try:
        _migrate(finance)
        moment = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
        today = moment.astimezone(ZONE).date()
        found = []
        for item in reminders(_rows(finance), today, _settings(finance)):
            local = datetime.fromisoformat(f"{item['booked_on']}T09:00").replace(tzinfo=ZONE)
            due = local.astimezone(timezone.utc)
            if moment.astimezone(timezone.utc) - timedelta(hours=24) <= due <= moment.astimezone(timezone.utc):
                found.append((f"finance:{item['code']}:{item['entry_id']}:{item['booked_on']}", due))
        return found
    finally:
        finance.close()
