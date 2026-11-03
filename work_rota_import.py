"""Approve reviewed rota rows into the existing shifts table, and undo only those rows."""
from __future__ import annotations

import json
import re

import planner_api
import work_rota_storage as storage

_KEY = re.compile(r'^[A-Za-z0-9._:-]{8,80}$')


class ImportError(storage.StorageError):
    pass


def _snapshot(row, fields):
    return json.dumps({name: row[name] for name in fields}, sort_keys=True, default=str)


def _shift_snapshot(row):
    return _snapshot(row, ('work_date', 'start_time', 'end_time', 'location_id', 'shift_type_id', 'break_minutes', 'notes'))


def approve(connection, import_id: str, body: dict):
    """Publish selected rows. The same idempotency key returns the original result."""
    storage.require_schema(connection)
    key = str((body or {}).get('idempotency_key') or '')
    if not _KEY.fullmatch(key):
        raise ImportError('Enter an idempotency key for this approval.', 'idempotency_required')
    selected = body.get('entries')
    if not isinstance(selected, list) or not selected:
        raise ImportError('Choose at least one row to approve.', 'nothing_selected')
    if len(selected) > 400:
        raise ImportError('Approve up to 400 rows at a time.', 'too_many_entries')
    if not connection.in_transaction:
        connection.execute('BEGIN IMMEDIATE')
    try:
        current = storage.get_import(connection, import_id)
        cached = storage.cached_approval(connection, import_id, key)
        if cached:
            connection.rollback()
            return cached
        if current['status'] in {'failed', 'cancelled'}:
            connection.rollback()
            raise ImportError('This import can no longer be approved.', 'import_closed', 409)
        result = {'created': [], 'leave': [], 'acknowledged': [], 'conflicts': [], 'duplicates': [], 'skipped': []}
        seen = set()
        for item in selected:
            entry_id = str((item or {}).get('id') or '')
            if entry_id in seen:
                continue
            seen.add(entry_id)
            _publish_one(connection, import_id, item, result)
        storage.store_approval(connection, import_id, key, result)
        storage.refresh_import_counts(connection, import_id)
        connection.commit()
        return result
    except Exception:
        connection.rollback()
        raise


def _publish_one(connection, import_id, item, result):
    entry_id = str((item or {}).get('id') or '')
    entry = storage._one(connection, 'SELECT * FROM work_rota_entries WHERE id=? AND import_id=?', (entry_id, import_id))
    if not entry:
        result['conflicts'].append({'entry_id': entry_id, 'message': 'That row is not in this import.'})
        return
    try:
        revision = int(item.get('revision'))
    except (TypeError, ValueError):
        result['conflicts'].append({'entry_id': entry_id, 'message': 'This row is out of date. Refresh it and try again.'})
        return
    if revision != int(entry['revision']):
        result['conflicts'].append({'entry_id': entry_id, 'message': 'This row was updated. Refresh it and try again.'})
        return
    if entry['review_status'] == 'rejected':
        result['skipped'].append({'entry_id': entry_id, 'message': 'This row was rejected.'})
        return
    if entry['review_status'] == 'imported':
        result['skipped'].append({'entry_id': entry_id, 'shift_id': entry.get('created_shift_id'), 'message': 'Already imported.'})
        return
    if entry.get('duplicate_shift_id'):
        result['duplicates'].append({'entry_id': entry_id, 'shift_id': entry['duplicate_shift_id'], 'message': 'This shift is already on the planner.'})
        return
    if not entry.get('approvable'):
        result['conflicts'].append({'entry_id': entry_id, 'message': 'Correct this row before approving it.'})
        return
    kind = entry['entry_kind']
    if kind == 'shift':
        _publish_shift(connection, entry, result)
    elif kind == 'leave':
        _publish_leave(connection, entry, result)
    elif kind in {'day_off', 'sickness'}:
        _acknowledge(connection, entry, result)
    else:
        result['conflicts'].append({'entry_id': entry['id'], 'message': 'Choose what this row means before approving it.'})


def _publish_shift(connection, entry, result):
    payload = {
        'work_date': entry['work_date'],
        'start_time': entry['start_time'],
        'end_time': entry['end_time'],
        'location_id': entry['location_id'],
        'shift_type_id': entry['shift_type_id'],
        'template_id': entry.get('template_id'),
        'break_minutes': 0,
        'notes': _safe_note(entry),
    }
    try:
        values = planner_api._shift_values(connection, payload)
        planner_api._check_shift(connection, values[0], values[7], values[8])
    except ValueError as error:
        result['conflicts'].append({'entry_id': entry['id'], 'message': str(error)})
        return
    existing = connection.execute(
        'SELECT id FROM shifts WHERE source_import_entry_id=?',
        (entry['id'],),
    ).fetchone()
    if existing:
        result['skipped'].append({'entry_id': entry['id'], 'shift_id': existing['id'], 'message': 'Already imported.'})
        return
    cursor = connection.execute(
        '''INSERT INTO shifts(work_date,template_id,location_id,shift_type_id,location_name,shift_type_name,
           colour,start_time,end_time,break_minutes,hours,notes,source_import_entry_id)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (*values, entry['id']),
    )
    shift_id = cursor.lastrowid
    planner_api._create_shift_alerts(connection, shift_id, values[0], values[7], values[4] + ' – ' + values[5])
    saved = storage._one(connection, 'SELECT * FROM shifts WHERE id=?', (shift_id,))
    stamp = storage.now()
    connection.execute(
        '''UPDATE work_rota_entries SET review_status='imported',created_shift_id=?,published_snapshot=?,
           revision=revision+1,updated_at=? WHERE id=?''',
        (shift_id, _shift_snapshot(saved), stamp, entry['id']),
    )
    result['created'].append({'entry_id': entry['id'], 'shift_id': shift_id, 'work_date': values[0]})


def _safe_note(entry) -> str:
    label = (entry.get('shift_label') or '').strip()
    department = (entry.get('department') or '').strip()
    note = label if label and label != department else ''
    return note[:200]


def _publish_leave(connection, entry, result):
    day = entry['work_date']
    if connection.execute('SELECT 1 FROM annual_leave WHERE leave_date=?', (day,)).fetchone():
        result['conflicts'].append({'entry_id': entry['id'], 'message': f'{day} is already annual leave.'})
        return
    if connection.execute('SELECT 1 FROM shifts WHERE work_date=?', (day,)).fetchone():
        result['conflicts'].append({'entry_id': entry['id'], 'message': f'{day} already has a shift.'})
        return
    cursor = connection.execute('INSERT INTO annual_leave(leave_date,notes) VALUES(?,?)', (day, ''))
    leave_id = cursor.lastrowid
    saved = storage._one(connection, 'SELECT * FROM annual_leave WHERE id=?', (leave_id,))
    snapshot = _snapshot(saved, ('leave_date', 'notes'))
    connection.execute(
        '''UPDATE work_rota_entries SET review_status='imported',created_leave_id=?,published_snapshot=?,
           revision=revision+1,updated_at=? WHERE id=?''',
        (leave_id, snapshot, storage.now(), entry['id']),
    )
    result['leave'].append({'entry_id': entry['id'], 'leave_id': leave_id, 'work_date': day})


def _acknowledge(connection, entry, result):
    snapshot = json.dumps({'entry_kind': entry['entry_kind'], 'work_date': entry['work_date']}, sort_keys=True)
    connection.execute(
        '''UPDATE work_rota_entries SET review_status='imported',published_snapshot=?,revision=revision+1,updated_at=?
           WHERE id=?''',
        (snapshot, storage.now(), entry['id']),
    )
    result['acknowledged'].append({'entry_id': entry['id'], 'entry_kind': entry['entry_kind'], 'work_date': entry['work_date']})


def undo(connection, import_id: str, body: dict | None = None):
    """Remove only rows this import created, and refuse rows the user has since changed."""
    storage.require_schema(connection)
    requested = (body or {}).get('entry_ids')
    if not connection.in_transaction:
        connection.execute('BEGIN IMMEDIATE')
    try:
        storage.get_import(connection, import_id)
        rows = storage.list_entries(connection, import_id)
        if requested is not None:
            if not isinstance(requested, list):
                raise ImportError('Choose the imported rows to undo.', 'invalid_undo')
            wanted = {str(item) for item in requested}
            rows = [row for row in rows if row['id'] in wanted]
        result = {'removed': [], 'conflicts': [], 'reopened': []}
        for entry in rows:
            if entry['review_status'] != 'imported':
                continue
            _undo_one(connection, entry, result)
        if result['conflicts']:
            connection.rollback()
            return {'removed': [], 'conflicts': result['conflicts'], 'reopened': []}
        storage.refresh_import_counts(connection, import_id)
        connection.commit()
        return result
    except Exception:
        connection.rollback()
        raise


def _undo_one(connection, entry, result):
    if entry.get('created_shift_id'):
        shift = storage._one(connection, 'SELECT * FROM shifts WHERE id=?', (entry['created_shift_id'],))
        if not shift:
            _reopen(connection, entry, result, 'The imported shift was already removed.')
            return
        if shift.get('source_import_entry_id') != entry['id']:
            result['conflicts'].append({'entry_id': entry['id'], 'message': 'This shift was not created by this import.'})
            return
        if _shift_snapshot(shift) != (entry.get('published_snapshot') or ''):
            result['conflicts'].append({'entry_id': entry['id'], 'message': 'This shift was changed after import, so it was left in place.'})
            return
        connection.execute('DELETE FROM shifts WHERE id=? AND source_import_entry_id=?', (shift['id'], entry['id']))
        _reopen(connection, entry, result, '')
        result['removed'].append({'entry_id': entry['id'], 'shift_id': shift['id']})
        return
    if entry.get('created_leave_id'):
        leave = storage._one(connection, 'SELECT * FROM annual_leave WHERE id=?', (entry['created_leave_id'],))
        if not leave:
            _reopen(connection, entry, result, 'The imported leave was already removed.')
            return
        snapshot = _snapshot(leave, ('leave_date', 'notes'))
        if snapshot != (entry.get('published_snapshot') or ''):
            result['conflicts'].append({'entry_id': entry['id'], 'message': 'This leave was changed after import, so it was left in place.'})
            return
        connection.execute('DELETE FROM annual_leave WHERE id=?', (leave['id'],))
        _reopen(connection, entry, result, '')
        result['removed'].append({'entry_id': entry['id'], 'leave_id': leave['id']})
        return
    _reopen(connection, entry, result, '')
    result['removed'].append({'entry_id': entry['id'], 'entry_kind': entry['entry_kind']})


def _reopen(connection, entry, result, message):
    connection.execute(
        '''UPDATE work_rota_entries SET review_status='pending',created_shift_id=NULL,created_leave_id=NULL,
           published_snapshot='',revision=revision+1,updated_at=? WHERE id=?''',
        (storage.now(), entry['id']),
    )
    if message:
        result['reopened'].append({'entry_id': entry['id'], 'message': message})
