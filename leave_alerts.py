"""Opt-in leave-now alerts for one account database.

The alert time starts from the saved journey. A configured live feed can move
it later, and the account weather setting can move it earlier. No address is
included in the notification.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('Europe/London')
STEPS = re.compile(r'\[Align travel steps\]\s*(\[[\s\S]*?\])\s*\[/Align travel steps\]')
ALLOWANCE = re.compile(r'Allowance:\s*(\d{1,3})\s+minutes', re.I)
KEY = 'leave_alerts'


def settings(raw):
    value = raw if isinstance(raw, dict) else {}
    try:
        window = int(value.get('window_minutes', 8))
    except (TypeError, ValueError):
        window = 8
    return {'enabled': bool(value.get('enabled')), 'window_minutes': min(30, max(1, window))}


def save_settings(body):
    if not isinstance(body, dict):
        raise ValueError('Leave alert settings must be an object.')
    try:
        window = int(body.get('window_minutes', 8))
    except (TypeError, ValueError):
        raise ValueError('Choose a check window between 1 and 30 minutes.') from None
    if not 1 <= window <= 30:
        raise ValueError('Choose a check window between 1 and 30 minutes.')
    return {'enabled': bool(body.get('enabled')), 'window_minutes': window}


def _when(value):
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZONE)
    return parsed.astimezone(timezone.utc)


def _journey_leave(notes, start):
    match = STEPS.search(notes or '')
    if not match:
        return None, None
    try:
        steps = json.loads(match.group(1))
    except (json.JSONDecodeError, TypeError):
        return None, None
    if not isinstance(steps, list) or not steps:
        return None, None
    first = steps[0]
    leave = _when(first.get('start'))
    if leave is None:
        return None, None
    allowance = ALLOWANCE.search(notes or '')
    if allowance:
        leave -= timedelta(minutes=int(allowance.group(1)))
    transit = next((step for step in steps if step.get('mode') in ('bus', 'train', 'rail')), None)
    return leave, transit


def _delay(transit, lookup):
    if not transit or lookup is None:
        return 0
    leg = {**transit, 'mode': 'rail' if transit.get('mode') == 'train' else transit.get('mode')}
    try:
        payload = lookup([leg]) or {}
    except Exception:
        return 0
    for update in payload.get('legs') or []:
        if update.get('service') != transit.get('service'):
            continue
        try:
            return max(0, int(update.get('delay_minutes') or 0))
        except (TypeError, ValueError):
            return 0
    return 0


def alert_time(row, now, delay_lookup=None, weather_lookup=None):
    """UTC time to notify, or None when this event should not alert."""
    if row['all_day']:
        return None
    start = _when(row['start_at'])
    if start is None or start < now or start > now + timedelta(hours=36):
        return None
    leave, transit = _journey_leave(row['notes'] or '', start)
    if leave is None:
        return None
    weather = 0
    if weather_lookup is not None:
        try:
            weather = max(0, int(weather_lookup(start) or 0))
        except Exception:
            weather = 0
    delay = _delay(transit, delay_lookup)
    when = leave - timedelta(minutes=weather) + timedelta(minutes=delay)
    title = ' '.join(str(row['title'] or 'your event').split())[:80]
    parts = [f'Time to leave for {title}.']
    if delay:
        parts.append(f'The service is {delay} minutes later.')
    if weather:
        parts.append(f'Weather adds {weather} minutes.')
    return when, ' '.join(parts), delay, weather


def due(connection, now, prefs, delay_lookup=None, weather_lookup=None):
    if not prefs.get('enabled'):
        return []
    window = timedelta(minutes=int(prefs.get('window_minutes') or 8))
    try:
        rows = connection.execute(
            "SELECT id, title, start_at, notes, all_day FROM organiser_events WHERE all_day=0"
        ).fetchall()
    except Exception:
        return []
    ready = []
    for row in rows:
        item = alert_time(row, now, delay_lookup, weather_lookup)
        if item is None:
            continue
        when, body, _delay_minutes, _weather = item
        if when <= now <= when + window:
            ready.append((f'leave:{row["id"]}', when, body))
    return ready
