"""A small cache of the next few days for the signed-in account.

Weather is copied from the account's existing forecast cache. This does not
call a weather or journey provider, and it does not invent a travel time.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('Europe/London')
TRAVEL = re.compile(
    r'\[Align travel\][\s\S]*?\[/Align travel\]|\[Align travel steps\][\s\S]*?\[/Align travel steps\]'
)
DAYS = 4


def _travel(notes):
    parts = [match.group(0).strip() for match in TRAVEL.finditer(notes or '')]
    return '\n'.join(parts)[:2000]


def pack(connection, now=None):
    now = (now or datetime.now(ZONE)).astimezone(ZONE)
    start = now.date()
    end = start + timedelta(days=DAYS)
    events = []
    try:
        rows = connection.execute(
            '''SELECT id, title, start_at, end_at, all_day, location, notes
               FROM organiser_events
               WHERE start_at >= ? AND start_at < ?
               ORDER BY start_at, id''',
            (start.isoformat(), end.isoformat()),
        ).fetchall()
    except Exception:
        rows = []
    for row in rows:
        events.append({
            'id': row['id'],
            'title': row['title'] or '',
            'start_at': row['start_at'] or '',
            'end_at': row['end_at'] or '',
            'all_day': bool(row['all_day']),
            'location': row['location'] or '',
            'travel': _travel(row['notes'] or ''),
        })
    shifts = []
    try:
        shift_rows = connection.execute(
            '''SELECT id, work_date, start_time, end_time, location_name, shift_type_name
               FROM shifts WHERE work_date >= ? AND work_date < ? ORDER BY work_date, start_time, id''',
            (start.isoformat(), end.isoformat()),
        ).fetchall()
    except Exception:
        shift_rows = []
    for row in shift_rows:
        shifts.append({
            'id': row['id'],
            'work_date': row['work_date'],
            'start_time': row['start_time'] or '',
            'end_time': row['end_time'] or '',
            'location_name': row['location_name'] or '',
            'shift_type_name': row['shift_type_name'] or '',
        })
    from weather_cache import read
    forecast = read(connection, 'weather_forecast_v1') or {}
    data = forecast.get('data') or {}
    daily = data.get('daily') or {}
    keys = ('time', 'temperature_2m_min', 'temperature_2m_max', 'weather_code', 'precipitation_probability_max')
    return {
        'generated_at': now.isoformat(timespec='minutes'),
        'from': start.isoformat(),
        'until': (end - timedelta(days=1)).isoformat(),
        'events': events,
        'shifts': shifts,
        'weather': {
            'cached': bool(forecast),
            'daily': {key: list(daily.get(key) or [])[:DAYS] for key in keys},
            'checked_at': forecast.get('checked_at') or '',
            'source': data.get('source') or '',
        },
    }
