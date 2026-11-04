"""Saved places, labels and section defaults for the guided planner screens."""
from __future__ import annotations

import re
import sqlite3

import travel_reminders

MODES = {'', 'drive', 'bus', 'train', 'transit'}
EMPTY_GUIDE = {
    'place_id': None,
    'travel_minutes': 45,
    'travel_mode': 'transit',
    'travel_info': '',
    'leave_alert_minutes': 60,
    'reminder_minutes': 30,
}


def _minutes(value, label: str) -> int:
    if value in (None, '', False):
        return 0
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f'Choose a valid {label}.') from error
    if number < 0 or number > travel_reminders.MAX_MINUTES:
        raise ValueError(f'{label} must be between 0 minutes and 1 week.')
    return number


def clean_type(value) -> str:
    text = ' '.join(str(value or 'Event').split())[:40]
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9 '&/-]{0,39}", text):
        raise ValueError('Use a short event type such as Appointment.')
    return text


def clean_label(value) -> str:
    text = ' '.join(str(value or '').split())[:40]
    if text and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 '&/-]{0,39}", text):
        raise ValueError('Use a short label, such as Health.')
    return text


def clean_mode(value) -> str:
    mode = str(value or 'transit').strip().lower()
    if mode not in MODES:
        raise ValueError('Choose a travel method.')
    return mode or 'transit'


def _place(item) -> tuple[str, str, bool, int | None]:
    if not isinstance(item, dict):
        raise ValueError('Each saved place needs a location.')
    name = ' '.join(str(item.get('name') or '').split())[:80]
    location = ' '.join(str(item.get('location') or '').split())[:240]
    if not location:
        raise ValueError('Add a location for each saved place.')
    place_id = item.get('id')
    try:
        place_id = int(place_id) if place_id else None
    except (TypeError, ValueError):
        place_id = None
    return name, location, bool(item.get('is_default')), place_id


def _rows(connection, sql, args=()):
    return [dict(row) for row in connection.execute(sql, args).fetchall()]


def places(connection, section_id=None) -> list[dict]:
    if section_id is None:
        return _rows(connection, 'SELECT id,name,location,section_id FROM saved_places ORDER BY LOWER(name), LOWER(location), id')
    return _rows(
        connection,
        'SELECT id,name,location,section_id FROM saved_places WHERE section_id=? ORDER BY id',
        (section_id,),
    )


def labels(connection) -> list[dict]:
    return _rows(connection, 'SELECT id,name,colour FROM planner_labels ORDER BY LOWER(name), id')


def guide_for(connection, section_id: int) -> dict:
    row = connection.execute('SELECT * FROM section_defaults WHERE section_id=?', (section_id,)).fetchone()
    guide = dict(EMPTY_GUIDE)
    if row:
        guide.update(dict(row))
    return guide


def catalog(connection) -> dict:
    return {'places': places(connection), 'labels': labels(connection)}


def attach(connection, section: dict) -> dict:
    try:
        section_id = section['id']
        guide = guide_for(connection, section_id)
        section['guide'] = guide
        section['places'] = places(connection, section_id)
        section['labels'] = labels(connection)
        ids = [event['id'] for event in section.get('events') or [] if event.get('source_kind') == 'align']
        if ids:
            marks = ','.join('?' * len(ids))
            details = {
                row['event_id']: row
                for row in connection.execute(
                    f'SELECT event_id,event_type,label_name,place_id FROM organiser_event_details WHERE event_id IN ({marks})',
                    ids,
                )
            }
            for event in section['events']:
                extra = details.get(event['id'])
                if extra:
                    event['event_type'] = extra['event_type']
                    event['label_name'] = extra['label_name']
                    event['place_id'] = extra['place_id']
    except sqlite3.OperationalError as error:
        raise ValueError('Section setup storage is not ready. Apply migration 158.') from error
    return section


def _ensure_label(connection, name: str) -> None:
    if not name:
        return
    found = connection.execute('SELECT id FROM planner_labels WHERE LOWER(name)=LOWER(?)', (name,)).fetchone()
    if found:
        return
    connection.execute("INSERT INTO planner_labels(name,colour) VALUES(?, '#16D9F2')", (name,))


def _remember_place(connection, section_id: int, name: str, location: str) -> int | None:
    name = ' '.join(str(name or '').split())[:80]
    location = ' '.join(str(location or '').split())[:240]
    if not location:
        raise ValueError('Add a location before saving the place.')
    found = connection.execute(
        '''SELECT id FROM saved_places
           WHERE section_id=? AND LOWER(name)=LOWER(?) AND LOWER(location)=LOWER(?)''',
        (section_id, name, location),
    ).fetchone()
    if found:
        return found['id']
    cursor = connection.execute(
        'INSERT INTO saved_places(name,location,section_id) VALUES(?,?,?)',
        (name, location, section_id),
    )
    return cursor.lastrowid


def save_places(connection, section_id: int, items) -> int | None:
    if not isinstance(items, list):
        raise ValueError('Saved places must be a list.')
    if len(items) > 40:
        raise ValueError('Save up to 40 places on a section.')
    cleaned = [_place(item) for item in items]
    existing = {row['id'] for row in places(connection, section_id)}
    kept = []
    default_id = None
    for name, location, is_default, supplied in cleaned:
        place_id = supplied if supplied in existing else None
        if place_id is None:
            found = connection.execute(
                '''SELECT id FROM saved_places
                   WHERE section_id=? AND LOWER(name)=LOWER(?) AND LOWER(location)=LOWER(?)''',
                (section_id, name, location),
            ).fetchone()
            place_id = found['id'] if found else None
        if place_id:
            connection.execute(
                'UPDATE saved_places SET name=?, location=? WHERE id=? AND section_id=?',
                (name, location, place_id, section_id),
            )
        else:
            cursor = connection.execute(
                'INSERT INTO saved_places(name,location,section_id) VALUES(?,?,?)',
                (name, location, section_id),
            )
            place_id = cursor.lastrowid
        kept.append(place_id)
        if is_default:
            default_id = place_id
    if default_id is None and kept:
        default_id = kept[0]
    if kept:
        marks = ','.join('?' * len(kept))
        connection.execute(
            f'DELETE FROM saved_places WHERE section_id=? AND id NOT IN ({marks})',
            (section_id, *kept),
        )
    else:
        connection.execute('DELETE FROM saved_places WHERE section_id=?', (section_id,))
    return default_id


def save_section(connection, section_id: int, payload: dict) -> None:
    guide = payload.get('guide') if isinstance(payload, dict) else None
    if not isinstance(guide, dict):
        return
    try:
        default_place = guide.get('place_id')
        if 'places' in guide:
            default_place = save_places(connection, section_id, guide.get('places') or [])
        elif default_place:
            default_place = int(default_place)
        else:
            default_place = None
        values = (
            section_id,
            default_place,
            _minutes(guide.get('travel_minutes', 45), 'travel time'),
            clean_mode(guide.get('travel_mode', 'transit')),
            str(guide.get('travel_info') or '').strip()[:500],
            _minutes(guide.get('leave_alert_minutes', 0), 'leave-by alert'),
            _minutes(guide.get('reminder_minutes', 0), 'event reminder'),
        )
        connection.execute(
            '''INSERT INTO section_defaults
               (section_id,place_id,travel_minutes,travel_mode,travel_info,leave_alert_minutes,reminder_minutes)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(section_id) DO UPDATE SET
                 place_id=excluded.place_id,
                 travel_minutes=excluded.travel_minutes,
                 travel_mode=excluded.travel_mode,
                 travel_info=excluded.travel_info,
                 leave_alert_minutes=excluded.leave_alert_minutes,
                 reminder_minutes=excluded.reminder_minutes''',
            values,
        )
    except sqlite3.OperationalError as error:
        raise ValueError('Section setup storage is not ready. Apply migration 158.') from error


def prepare_event(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return payload
    if not any(key in payload for key in ('leave_alert_minutes', 'reminder_minutes', 'travel_info')):
        return payload
    data = dict(payload)
    leave = 0 if data.get('all_day') else _minutes(data.get('leave_alert_minutes', 0), 'leave-by alert')
    reminder = _minutes(data.get('reminder_minutes', 0), 'event reminder')
    data['notes'] = travel_reminders.with_guide(
        data.get('notes', ''),
        leave,
        reminder,
        data.get('travel_info') or '',
    )
    return data


def save_event(connection, event_id: int, section_id: int, payload: dict) -> None:
    if not isinstance(payload, dict):
        return
    if not any(key in payload for key in ('event_type', 'label_name', 'save_place', 'place_id')):
        return
    try:
        event_type = clean_type(payload.get('event_type') or 'Event')
        label = clean_label(payload.get('label_name') or '')
        _ensure_label(connection, label)
        place_id = None
        if payload.get('save_place'):
            place_id = _remember_place(
                connection,
                section_id,
                payload.get('place_name') or payload.get('title') or '',
                payload.get('location') or '',
            )
        elif payload.get('place_id'):
            try:
                place_id = int(payload.get('place_id'))
            except (TypeError, ValueError):
                place_id = None
        connection.execute(
            '''INSERT INTO organiser_event_details(event_id,event_type,label_name,place_id)
               VALUES(?,?,?,?)
               ON CONFLICT(event_id) DO UPDATE SET
                 event_type=excluded.event_type,
                 label_name=excluded.label_name,
                 place_id=excluded.place_id''',
            (event_id, event_type, label, place_id),
        )
    except sqlite3.OperationalError as error:
        raise ValueError('Section setup storage is not ready. Apply migration 158.') from error
