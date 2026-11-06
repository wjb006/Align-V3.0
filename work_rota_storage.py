"""Account-scoped rota import sessions and pending entries."""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone

import rota_parser

IMPORT_STATUSES = {'processing', 'review', 'partially_imported', 'imported', 'failed', 'cancelled'}


class StorageError(ValueError):
    def __init__(self, message, code='invalid_rota', status=400):
        super().__init__(message)
        self.code = code
        self.status = status


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_id() -> str:
    return secrets.token_hex(16)


def schema_ready(connection) -> bool:
    if not _has_table(connection, 'work_rota_imports') or not _has_table(connection, 'work_rota_entries'):
        return False
    return 'source_import_entry_id' in _columns(connection, 'shifts')


def require_schema(connection):
    if not schema_ready(connection):
        raise StorageError(
            'Rota import is not available until the database update has been applied.',
            'rota_schema_unavailable',
            400,
        )


def _has_table(connection, name: str) -> bool:
    if hasattr(connection, 'schema'):
        row = connection.execute(
            'SELECT 1 FROM information_schema.tables WHERE table_schema=? AND table_name=?',
            (connection.schema, name),
        ).fetchone()
    else:
        row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
    return bool(row)


def _columns(connection, table: str) -> set[str]:
    if hasattr(connection, 'schema'):
        rows = connection.execute(
            'SELECT column_name FROM information_schema.columns WHERE table_schema=? AND table_name=?',
            (connection.schema, table),
        ).fetchall()
        return {row[0] for row in rows}
    return {row[1] for row in connection.execute(f'PRAGMA table_info({table})')}


def _one(connection, sql, args=()):
    row = connection.execute(sql, args).fetchone()
    return dict(row) if row else None


def _all(connection, sql, args=()):
    return [dict(row) for row in connection.execute(sql, args).fetchall()]


def catalog(connection):
    return {
        'locations': _all(connection, 'SELECT id,name,colour,active FROM locations WHERE active=1 ORDER BY name'),
        'shift_types': _all(connection, 'SELECT id,name,colour,active FROM shift_types WHERE active=1 ORDER BY name'),
        'templates': _all(connection, '''SELECT id,location_id,shift_type_id,label,start_time,end_time,active
            FROM shift_templates WHERE active=1 ORDER BY label'''),
    }


def create_import(connection, file_count: int) -> dict:
    require_schema(connection)
    import_id = new_id()
    stamp = now()
    connection.execute(
        '''INSERT INTO work_rota_imports(
            id,status,source_file_count,candidate_count,created_count,skipped_count,
            error_code,notice_codes,created_at,updated_at)
           VALUES(?,?,?,0,0,0,'','[]',?,?)''',
        (import_id, 'processing', file_count, stamp, stamp),
    )
    return get_import(connection, import_id)


def get_import(connection, import_id: str):
    require_schema(connection)
    row = _one(connection, 'SELECT * FROM work_rota_imports WHERE id=?', (import_id,))
    if not row:
        raise StorageError('That rota import could not be found.', 'not_found', 404)
    row['notice_codes'] = json.loads(row.get('notice_codes') or '[]')
    return row


def list_entries(connection, import_id: str):
    require_schema(connection)
    return _all(connection, '''SELECT * FROM work_rota_entries WHERE import_id=?
        ORDER BY work_date,start_time,id''', (import_id,))


def public_entry(row: dict) -> dict:
    confidence = float(row.get('confidence') or 0)
    return {
        'id': row['id'],
        'work_date': row.get('work_date') or '',
        'source_date_text': row.get('source_date_text') or '',
        'start_time': row.get('start_time') or '',
        'end_time': row.get('end_time') or '',
        'shift_label': row.get('shift_label') or '',
        'department': row.get('department') or '',
        'location_id': row.get('location_id'),
        'location_text': row.get('location_text') or '',
        'shift_type_id': row.get('shift_type_id'),
        'template_id': row.get('template_id'),
        'entry_kind': row.get('entry_kind') or 'unknown',
        'confidence': confidence,
        'confidence_band': 'high' if confidence >= rota_parser.HIGH_CONFIDENCE else 'medium' if confidence >= rota_parser.MEDIUM_CONFIDENCE else 'low',
        'review_status': row.get('review_status') or 'pending',
        'approvable': bool(row.get('approvable')),
        'preselected': bool(row.get('approvable') and confidence >= rota_parser.HIGH_CONFIDENCE),
        'ambiguity': row.get('ambiguity') or '',
        'duplicate_shift_id': row.get('duplicate_shift_id'),
        'created_shift_id': row.get('created_shift_id'),
        'created_leave_id': row.get('created_leave_id'),
        'revision': row.get('revision') or 1,
    }


def save_drafts(connection, import_id: str, drafts, notices, error_code=''):
    require_schema(connection)
    choices = catalog(connection)
    stamp = now()
    kept = 0
    for draft in drafts:
        if kept >= 400:
            notices = list(dict.fromkeys([*notices, 'too_many_entries']))
            break
        scored = rota_parser.match_catalog(draft, choices)
        duplicate = _duplicate_shift(connection, scored)
        if duplicate:
            scored['duplicate_shift_id'] = duplicate
            scored = rota_parser.score_entry(scored)
        connection.execute(
            '''INSERT INTO work_rota_entries(
                id,import_id,work_date,source_date_text,start_time,end_time,shift_label,department,
                location_id,location_text,shift_type_id,template_id,entry_kind,confidence,review_status,
                duplicate_shift_id,ambiguity,approvable,fingerprint,revision,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'pending',?,?,?,?,1,?,?)''',
            (
                new_id(), import_id, scored.get('work_date'), scored.get('source_date_text') or '',
                scored.get('start_time') or '', scored.get('end_time') or '', scored.get('shift_label') or '',
                scored.get('department') or '', scored.get('location_id'), scored.get('location_text') or '',
                scored.get('shift_type_id'), scored.get('template_id'), scored.get('entry_kind') or 'unknown',
                scored.get('confidence') or 0, scored.get('duplicate_shift_id'), scored.get('ambiguity') or '',
                int(scored.get('approvable') or 0), scored.get('fingerprint') or '', stamp, stamp,
            ),
        )
        kept += 1
    status = 'failed' if error_code and kept == 0 else 'review'
    connection.execute(
        '''UPDATE work_rota_imports SET status=?,candidate_count=?,error_code=?,notice_codes=?,updated_at=?,
           completed_at=? WHERE id=?''',
        (status, kept, error_code, json.dumps(list(dict.fromkeys(notices))), stamp, stamp if status == 'failed' else None, import_id),
    )
    return get_import(connection, import_id)


def mark_failed(connection, import_id: str, code: str):
    stamp = now()
    connection.execute(
        '''UPDATE work_rota_imports SET status='failed',error_code=?,updated_at=?,completed_at=? WHERE id=?''',
        (code, stamp, stamp, import_id),
    )


def _duplicate_shift(connection, entry):
    if not entry.get('work_date') or entry.get('entry_kind') != 'shift' or not entry.get('start_time') or not entry.get('end_time'):
        return None
    if entry.get('location_id'):
        row = connection.execute(
            '''SELECT id FROM shifts WHERE work_date=? AND start_time=? AND end_time=? AND location_id=? LIMIT 1''',
            (entry['work_date'], entry['start_time'], entry['end_time'], entry['location_id']),
        ).fetchone()
    else:
        row = connection.execute(
            '''SELECT id FROM shifts WHERE work_date=? AND start_time=? AND end_time=? AND lower(location_name)=lower(?) LIMIT 1''',
            (entry['work_date'], entry['start_time'], entry['end_time'], entry.get('location_text') or ''),
        ).fetchone()
    return row['id'] if row else None


def update_entry(connection, import_id: str, entry_id: str, patch: dict):
    require_schema(connection)
    current = _one(connection, 'SELECT * FROM work_rota_entries WHERE id=? AND import_id=?', (entry_id, import_id))
    if not current:
        raise StorageError('That rota row could not be found.', 'not_found', 404)
    if current['review_status'] == 'imported':
        raise StorageError('Imported rows are changed from the planner, or undone first.', 'already_imported', 409)
    try:
        expected = int(patch.get('revision'))
    except (TypeError, ValueError) as error:
        raise StorageError('This row is out of date. Refresh it and try again.', 'revision_conflict', 409) from error
    if expected != int(current['revision']):
        raise StorageError('This row was updated. Refresh it and try again.', 'revision_conflict', 409)
    try:
        scored = rota_parser.apply_correction(current, patch)
    except rota_parser.ParseProblem as error:
        raise StorageError(str(error), error.code) from error
    # A user can save a previously unseen workplace or shift area while
    # reviewing their rota. This avoids a separate setup wizard and teaches
    # the private catalogue only from an explicit review action.
    if patch.get('create_location'):
        name = rota_parser.clean_text(patch.get('new_location_name') or scored.get('location_text'), 80)
        if not name:
            raise StorageError('Enter a workplace name before saving it.', 'invalid_location')
        address = rota_parser.clean_text(patch.get('new_location_address') or '', 1000)
        existing = connection.execute('SELECT id,active FROM locations WHERE lower(name)=lower(?) LIMIT 1', (name,)).fetchone()
        if existing:
            location_id = int(existing['id'])
            if not existing['active']:
                connection.execute('UPDATE locations SET active=1 WHERE id=?', (location_id,))
        else:
            cursor = connection.execute(
                'INSERT INTO locations(name,address,colour) VALUES(?,?,?)',
                (name, address, '#365CE6'),
            )
            location_id = int(cursor.lastrowid)
        scored['location_id'] = location_id
        scored['location_text'] = name
    if patch.get('create_shift_type'):
        name = rota_parser.clean_text(patch.get('new_shift_type_name') or scored.get('department') or scored.get('shift_label'), 80)
        if not name:
            raise StorageError('Enter a shift area before saving it.', 'invalid_shift_type')
        existing = connection.execute('SELECT id,active FROM shift_types WHERE lower(name)=lower(?) LIMIT 1', (name,)).fetchone()
        if existing:
            shift_type_id = int(existing['id'])
            if not existing['active']:
                connection.execute('UPDATE shift_types SET active=1 WHERE id=?', (shift_type_id,))
        else:
            cursor = connection.execute(
                'INSERT INTO shift_types(name,colour) VALUES(?,?)',
                (name, '#3B82F6'),
            )
            shift_type_id = int(cursor.lastrowid)
        scored['shift_type_id'] = shift_type_id
        scored['department'] = name
    if scored.get('location_id') and scored.get('shift_type_id'):
        connection.execute(
            'INSERT INTO location_shift_types(location_id,shift_type_id) VALUES(?,?) ON CONFLICT(location_id,shift_type_id) DO NOTHING',
            (int(scored['location_id']), int(scored['shift_type_id'])),
        )
    _validate_links(connection, scored)
    duplicate = _duplicate_shift(connection, scored)
    scored['duplicate_shift_id'] = duplicate
    scored = rota_parser.score_entry(scored)
    stamp = now()
    revision = int(current['revision']) + 1
    connection.execute(
        '''UPDATE work_rota_entries SET work_date=?,start_time=?,end_time=?,shift_label=?,department=?,
           location_id=?,location_text=?,shift_type_id=?,template_id=?,entry_kind=?,confidence=?,
           review_status=?,duplicate_shift_id=?,ambiguity=?,approvable=?,fingerprint=?,revision=?,updated_at=?
           WHERE id=? AND import_id=? AND revision=?''',
        (
            scored.get('work_date'), scored.get('start_time') or '', scored.get('end_time') or '',
            scored.get('shift_label') or '', scored.get('department') or '', scored.get('location_id'),
            scored.get('location_text') or '', scored.get('shift_type_id'), scored.get('template_id'),
            scored.get('entry_kind') or 'unknown', scored.get('confidence') or 0,
            scored.get('review_status') or current['review_status'], scored.get('duplicate_shift_id'),
            scored.get('ambiguity') or '', int(scored.get('approvable') or 0), scored.get('fingerprint') or '',
            revision, stamp, entry_id, import_id, current['revision'],
        ),
    )
    connection.execute('UPDATE work_rota_imports SET updated_at=? WHERE id=?', (stamp, import_id))
    return _one(connection, 'SELECT * FROM work_rota_entries WHERE id=?', (entry_id,))


def _validate_links(connection, entry):
    if entry.get('location_id'):
        row = connection.execute('SELECT id FROM locations WHERE id=? AND active=1', (int(entry['location_id']),)).fetchone()
        if not row:
            raise StorageError('Choose a saved work location.', 'invalid_location')
        entry['location_id'] = int(entry['location_id'])
    if entry.get('shift_type_id'):
        row = connection.execute('SELECT id FROM shift_types WHERE id=? AND active=1', (int(entry['shift_type_id']),)).fetchone()
        if not row:
            raise StorageError('Choose a saved shift area.', 'invalid_shift_type')
        entry['shift_type_id'] = int(entry['shift_type_id'])
    if entry.get('template_id'):
        row = connection.execute('SELECT id FROM shift_templates WHERE id=? AND active=1', (int(entry['template_id']),)).fetchone()
        if not row:
            raise StorageError('Choose a saved shift pattern.', 'invalid_template')
        entry['template_id'] = int(entry['template_id'])


def refresh_import_counts(connection, import_id: str):
    rows = list_entries(connection, import_id)
    created = sum(1 for row in rows if row['review_status'] == 'imported')
    pending = sum(1 for row in rows if row['review_status'] == 'pending')
    skipped = sum(1 for row in rows if row['review_status'] == 'rejected' or row.get('duplicate_shift_id'))
    if created and pending:
        status = 'partially_imported'
    elif created and not pending:
        status = 'imported'
    else:
        status = 'review'
    stamp = now()
    connection.execute(
        '''UPDATE work_rota_imports SET status=?,created_count=?,skipped_count=?,updated_at=?,completed_at=? WHERE id=?''',
        (status, created, skipped, stamp, stamp if status == 'imported' else None, import_id),
    )
    return get_import(connection, import_id)


def delete_import(connection, import_id: str):
    current = get_import(connection, import_id)
    if current['status'] in {'imported', 'partially_imported'} or current['created_count']:
        raise StorageError('Undo the imported rows before deleting this review.', 'import_not_empty', 409)
    connection.execute('DELETE FROM work_rota_imports WHERE id=?', (import_id,))


def cached_approval(connection, import_id: str, key: str):
    row = _one(connection, 'SELECT result_json FROM work_rota_approvals WHERE import_id=? AND idempotency_key=?', (import_id, key))
    return json.loads(row['result_json']) if row else None


def store_approval(connection, import_id: str, key: str, result: dict):
    connection.execute(
        'INSERT INTO work_rota_approvals(import_id,idempotency_key,result_json,created_at) VALUES(?,?,?,?)',
        (import_id, key, json.dumps(result), now()),
    )
