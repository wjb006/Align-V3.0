"""Match shifts to the Work iCloud calendar and describe that link.

Shifts stay in the shifts table. This module only decides which linked
calendar they belong to, using a normalised name so emoji, spelling and
invisible Unicode markers do not hide "Work" or "Work Calendar".
"""
from __future__ import annotations

import logging
import unicodedata

import planner_api

LOG = logging.getLogger('align.icloud')
_MARKS = str.maketrans('', '', '\uFE0E\uFE0F\u200B\u200C\u200D\u2060')


def calendar_label(name: str) -> str:
    """Return a comparable calendar label with emoji and punctuation removed."""
    text = unicodedata.normalize('NFKC', str(name or '')).translate(_MARKS)
    kept = []
    for char in text:
        category = unicodedata.category(char)
        if category.startswith(('L', 'N')) or char.isspace():
            kept.append(char)
        elif category.startswith('P'):
            kept.append(' ')
    words = []
    for word in ''.join(kept).casefold().split():
        words.append('calendar' if word in {'calendar', 'calender'} else word)
    return ' '.join(words)


def is_work_calendar_name(name: str) -> bool:
    return calendar_label(name) in {'work', 'work calendar'}


def _rank(name: str) -> int | None:
    label = calendar_label(name)
    if label == 'work calendar':
        return 0
    if label == 'work':
        return 1
    return None


def find_work_link(connection) -> dict | None:
    """Return the active section linked to a Work / Work Calendar calendar."""
    rows = connection.execute(
        """SELECT s.id AS section_id, s.name AS section_name,
                  l.calendar_url, l.calendar_name, l.export_enabled
             FROM organiser_sections s
             JOIN calendar_links l
               ON l.target_kind='organiser_section' AND l.target_key=CAST(s.id AS TEXT)
            WHERE s.active=1"""
    ).fetchall()
    ranked = []
    for row in rows:
        item = dict(row)
        scores = [score for score in (_rank(item.get('calendar_name') or ''), _rank(item.get('section_name') or '')) if score is not None]
        if not scores:
            continue
        ranked.append((min(scores), 0 if item.get('export_enabled') else 1, int(item['section_id']), item))
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[:3])
    return ranked[0][3]


def status(connection) -> dict:
    """Describe where shifts will appear. No shift details are included."""
    link = None
    count = 0
    try:
        link = find_work_link(connection)
        if planner_api._has_table(connection, 'shifts'):
            count = int(connection.execute('SELECT COUNT(*) FROM shifts').fetchone()[0])
    except Exception as error:
        LOG.error('Work calendar status failed: %s', type(error).__name__)
        return {
            'linked': False, 'name': '', 'section_id': None, 'export_enabled': False,
            'shift_count': 0, 'message': 'Work calendar status is unavailable. Shifts already saved in Align are unchanged.',
        }
    name = ''
    if link:
        name = str(link.get('calendar_name') or link.get('section_name') or 'Work')
    export = bool(link and link.get('calendar_url') and link.get('export_enabled'))
    linked = bool(link and link.get('calendar_url'))
    if export:
        message = f'Shifts are saved on {name} and queued for iCloud.'
    elif linked:
        message = f'Shifts are saved on {name}. iCloud export is turned off for that calendar.'
    else:
        message = 'Shifts are saved in Align. Link an iCloud calendar named Work or Work Calendar to sync them.'
    return {
        'linked': linked,
        'name': name,
        'section_id': int(link['section_id']) if link else None,
        'export_enabled': export,
        'shift_count': count,
        'message': message,
    }


def shift_records(connection, start_date: str | None = None) -> list[dict]:
    """Project saved shifts into calendar fields. Invalid rows are skipped."""
    if not planner_api._has_table(connection, 'shifts'):
        return []
    sql = """SELECT s.id,s.work_date,s.start_time,s.end_time,s.location_name,s.shift_type_name,s.notes,
                    l.address AS location
               FROM shifts s LEFT JOIN locations l ON l.id=s.location_id"""
    args: tuple = ()
    if start_date:
        sql += ' WHERE s.work_date>=?'
        args = (start_date,)
    sql += ' ORDER BY s.work_date,s.start_time,s.id'
    records = []
    for row in connection.execute(sql, args):
        item = dict(row)
        try:
            start, end = planner_api._bounds(item['work_date'], item['start_time'], item['end_time'])
        except (TypeError, ValueError):
            continue
        title = ' – '.join(part for part in (item.get('location_name'), item.get('shift_type_name')) if part) or 'Work shift'
        records.append({
            'id': item['id'],
            'title': title[:200],
            'start_at': start.isoformat(timespec='minutes'),
            'end_at': end.isoformat(timespec='minutes'),
            'all_day': 0,
            'location': str(item.get('location') or '')[:1000],
            'notes': str(item.get('notes') or '')[:4000],
            'work_date': item['work_date'],
            'location_name': item.get('location_name') or '',
            'shift_type_name': item.get('shift_type_name') or '',
            'source_kind': 'shift',
        })
    return records


def section_shifts(connection, section_id: int, start_date: str) -> list[dict]:
    link = find_work_link(connection)
    if not link or int(link['section_id']) != int(section_id):
        return []
    return section_shift_events(shift_records(connection, start_date), int(section_id))


def section_shift_events(records: list[dict], section_id: int) -> list[dict]:
    return [{**record, 'section_id': section_id} for record in records]
