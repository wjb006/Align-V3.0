"""Transactional work-pattern setup. Existing scheduled shifts are never rewritten."""
import hashlib
import json
import math
import re
from datetime import datetime, timedelta

DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def colour(value):
    value = str(value)
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
        raise ValueError('Choose a valid colour (for example #365CE6).')
    return value.upper()


def bounded_number(value, label, minimum, maximum, integer=False):
    try:
        number = float(value)
    except (ValueError, TypeError):
        raise ValueError(f'Enter a valid {label}.') from None
    if not math.isfinite(number) or not minimum <= number <= maximum or (integer and number != int(number)):
        raise ValueError(f'{label.capitalize()} must be between {minimum} and {maximum}.')
    return int(number) if integer else number


def slot_value(item):
    try:
        start = datetime.strptime(str(item['start_time']), '%H:%M')
    except (ValueError, KeyError):
        raise ValueError('Enter a valid start time.') from None
    duration = bounded_number(item.get('duration_minutes'), 'duration in minutes', 1, 1439, True)
    rest = bounded_number(item.get('break_minutes', 0), 'break in minutes', 0, duration - 1, True)
    start_text = start.strftime('%H:%M')
    return {'key': f'{start_text}-{duration}-{rest}', 'start_time': start_text,
            'duration_minutes': duration, 'break_minutes': rest,
            'end_time': (start + timedelta(minutes=duration)).strftime('%H:%M')}


def revision(connection):
    content = {}
    for table in ('locations', 'shift_types', 'shift_templates', 'location_shift_types'):
        content[table] = [tuple(row) for row in connection.execute(f'SELECT * FROM {table} ORDER BY 1,2')]
    content['settings'] = [tuple(row) for row in connection.execute(
        "SELECT * FROM settings WHERE setting_key IN ('contracted_hours','rate_of_pay','standard_shift_minutes','work_setup_library','work_setup_area_slots','leave_allowance_days','leave_year_start','minimum_rest_hours') ORDER BY setting_key")]
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def load_setup(connection):
    settings = {row['setting_key']: row['setting_value'] for row in connection.execute('SELECT setting_key,setting_value FROM settings').fetchall()}
    slots = {item['key']: item for item in json.loads(settings.get('work_setup_library', '[]'))}
    locations = [dict(row) for row in connection.execute('SELECT * FROM locations WHERE active=1 ORDER BY name')]
    areas = [dict(row) for row in connection.execute('SELECT * FROM shift_types WHERE active=1 ORDER BY name')]
    saved_area_slots = json.loads(settings.get('work_setup_area_slots', '{}'))
    for item in locations:
        item['key'] = f"l{item['id']}"
    for item in areas:
        item['key'] = f"a{item['id']}"
        item['slots'] = [key for key in saved_area_slots.get(str(item['id']), []) if key in slots]
    assignments = []
    for row in connection.execute('''SELECT t.* FROM shift_templates t
            JOIN locations l ON l.id=t.location_id JOIN shift_types s ON s.id=t.shift_type_id
            WHERE t.active=1 AND l.active=1 AND s.active=1 ORDER BY t.id'''):
        start = datetime.strptime(row['start_time'], '%H:%M')
        end = datetime.strptime(row['end_time'], '%H:%M')
        duration = int((end - start).total_seconds() / 60) % 1440 or 1440
        slot = {'key': f"{row['start_time']}-{duration}-{row['break_minutes']}",
                'start_time': row['start_time'], 'duration_minutes': duration,
                'break_minutes': row['break_minutes'], 'end_time': row['end_time']}
        slots[slot['key']] = slot
        area = next(item for item in areas if item['id'] == row['shift_type_id'])
        if slot['key'] not in area['slots']:
            area['slots'].append(slot['key'])
        assignments.append({'location_key': f"l{row['location_id']}", 'area_key': area['key'],
                            'slot_key': slot['key'], 'days': json.loads(row['applicable_days']) or DAYS[:]})
    return {'revision': revision(connection), 'contracted_hours': float(settings.get('contracted_hours', '0')),
            'rate_of_pay': float(settings.get('rate_of_pay', '0')),
            'duration_minutes': int(settings.get('standard_shift_minutes', '240')),
            'leave_allowance_days': int(float(settings.get('leave_allowance_days', '0') or 0)),
            'leave_year_start': settings.get('leave_year_start') or '01-01',
            'minimum_rest_hours': float(settings.get('minimum_rest_hours', '0') or 0),
            'slots': sorted(slots.values(), key=lambda item: (item['start_time'], item['duration_minutes'])),
            'locations': locations, 'areas': areas, 'assignments': assignments}


def save_setup(connection, payload):
    # Acquire the write lock before checking the token, so two tabs cannot silently
    # overwrite each other's newer location/day configuration.
    connection.execute('BEGIN')
    if payload.get('revision') != revision(connection):
        raise ValueError('Work Settings changed in another tab. Cancel this edit and reopen it before saving.')
    # Save initial library entries independently; only linked choices become patterns.
    partial = payload.get('save_mode') == 'settings'
    contracted = bounded_number(payload.get('contracted_hours'), 'contracted weekly hours', 0, 168)
    duration = bounded_number(payload.get('duration_minutes'), 'standard duration in minutes', 1, 1439, True)
    for name, limit in [('slots', 100), ('locations', 50), ('areas', 50), ('assignments', 1000)]:
        if not isinstance(payload.get(name), list) or not (0 if partial else 1) <= len(payload[name]) <= limit:
            raise ValueError(f'Check the {name} list (maximum {limit}).')
    slots = {}
    canonical_keys = set()
    for raw in payload['slots']:
        key = str(raw.get('key', ''))
        slot = slot_value(raw)
        if not key or key in slots or slot['key'] in canonical_keys:
            raise ValueError('Start-time and duration options must be unique.')
        slots[key] = slot
        canonical_keys.add(slot['key'])
    maps = {}
    for table, group in [('locations', 'locations'), ('shift_types', 'areas')]:
        maps[group] = {}
        names, ids = set(), set()
        for raw in payload[group]:
            key, name = str(raw.get('key', '')), str(raw.get('name', '')).strip()
            if not key or key in maps[group] or not name or len(name) > 80 or name.casefold() in names:
                raise ValueError(f'Give each {group} entry a unique name (up to 80 characters).')
            names.add(name.casefold())
            item_id = raw.get('id')
            if item_id:
                row = connection.execute(f'SELECT id FROM {table} WHERE id=? AND active=1', (item_id,)).fetchone()
                if not row or item_id in ids:
                    raise ValueError(f'An existing {group} entry is no longer available.')
                ids.add(item_id)
            # Prevent accidental creation of a second case-insensitive copy, or
            # un-hiding an admin-disabled location/type through setup.
            duplicate = connection.execute(f'SELECT id FROM {table} WHERE lower(name)=lower(?) AND id<>?', (name, item_id or 0)).fetchone()
            if duplicate:
                raise ValueError(f'{name} already exists. Use its existing entry, or edit it in Admin.')
            if group == 'locations':
                address = str(raw.get('address', '')).strip()
                if not address or len(address) > 1000:
                    raise ValueError(f'Enter an address for {name}.')
                values = (name, address, colour(raw.get('colour', '#365CE6')))
                if item_id:
                    from travel_refresh import location_changed
                    previous=connection.execute('SELECT address FROM locations WHERE id=?',(item_id,)).fetchone()
                    location_changed(connection, previous[0], address)
                    connection.execute('UPDATE locations SET name=?,address=?,colour=? WHERE id=?', (*values, item_id))
                else:
                    item_id = connection.execute('INSERT INTO locations(name,address,colour) VALUES(?,?,?)', values).lastrowid
            else:
                if not isinstance(raw.get('slots'), list) or (not partial and not raw['slots']) or any(key not in slots for key in raw['slots']):
                    raise ValueError(f'Choose at least one saved time for {name}.')
                if item_id:
                    current = connection.execute('SELECT colour FROM shift_types WHERE id=?', (item_id,)).fetchone()
                    connection.execute('UPDATE shift_types SET name=?,colour=? WHERE id=?', (name, colour(raw.get('colour', current['colour'])), item_id))
                else:
                    item_id = connection.execute('INSERT INTO shift_types(name,colour) VALUES(?,?)', (name, colour(raw.get('colour', '#3B82F6')))).lastrowid
            maps[group][key] = item_id
    # The wizard must include every active record it loaded. Omissions do not
    # constitute permission to delete or hide locations or categories.
    for table, group in [('locations', 'locations'), ('shift_types', 'areas')]:
        if {row[0] for row in connection.execute(f'SELECT id FROM {table} WHERE active=1')} != set(maps[group].values()):
            raise ValueError(f'Keep all saved {group} entries in setup. Use Admin to hide an entry.')
    keep, combinations, used_locations, used_areas = set(), set(), set(), set()
    visible_ids = [row[0] for row in connection.execute('''SELECT t.id FROM shift_templates t
        JOIN locations l ON l.id=t.location_id JOIN shift_types s ON s.id=t.shift_type_id
        WHERE t.active=1 AND l.active=1 AND s.active=1''')]
    areas_by_key = {item['key']: item for item in payload['areas']}
    for item in payload['assignments']:
        lk, ak, sk = item.get('location_key'), item.get('area_key'), item.get('slot_key')
        if lk not in maps['locations'] or ak not in maps['areas'] or sk not in slots or sk not in areas_by_key[ak]['slots']:
            raise ValueError('A location, area or time assignment is invalid.')
        combination = (lk, ak, sk)
        if combination in combinations:
            raise ValueError('Each location, area and time combination may only be assigned once.')
        combinations.add(combination)
        used_locations.add(lk)
        used_areas.add(ak)
        days = item.get('days')
        if not isinstance(days, list) or not days or any(day not in DAYS for day in days):
            raise ValueError('Choose at least one weekday for every assigned shift.')
        days = json.dumps([day for day in DAYS if day in days])
        slot = slots[sk]
        location_id, area_id = maps['locations'][lk], maps['areas'][ak]
        period = 'AM' if slot['start_time'] < '12:00' else 'PM'
        match = connection.execute('''SELECT id FROM shift_templates WHERE location_id=? AND shift_type_id=?
            AND start_time=? AND end_time=? AND break_minutes=? ORDER BY active DESC,id LIMIT 1''',
            (location_id, area_id, slot['start_time'], slot['end_time'], slot['break_minutes'])).fetchone()
        if match:
            template_id = match['id']
            connection.execute('UPDATE shift_templates SET sub_shift_type=?,applicable_days=?,active=1 WHERE id=?', (period, days, template_id))
        else:
            label = f"{areas_by_key[ak]['name']} {period} {slot['start_time']}–{slot['end_time']} ({slot['break_minutes']}m)"
            template_id = connection.execute('''INSERT INTO shift_templates
                (location_id,shift_type_id,label,sub_shift_type,start_time,end_time,break_minutes,applicable_days)
                VALUES(?,?,?,?,?,?,?,?)''', (location_id, area_id, label, period, slot['start_time'], slot['end_time'], slot['break_minutes'], days)).lastrowid
        keep.add(template_id)
        connection.execute('INSERT OR IGNORE INTO location_shift_types VALUES(?,?)', (location_id, area_id))
    complete = bool(keep) and used_locations == set(maps['locations']) and used_areas == set(maps['areas'])
    if not partial and not complete:
        raise ValueError('Assign at least one shift to every location and area before saving.')
    for template_id in set(visible_ids) - keep:
        connection.execute('UPDATE shift_templates SET active=0 WHERE id=?', (template_id,))
    existing = {row['setting_key']: row['setting_value'] for row in connection.execute('SELECT setting_key,setting_value FROM settings').fetchall()}
    pay = bounded_number(payload.get('rate_of_pay', existing.get('rate_of_pay', '0')), 'rate of pay', 0, 100000)
    allowance = bounded_number(payload.get('leave_allowance_days', existing.get('leave_allowance_days', '0')), 'leave allowance', 0, 366, True)
    rest = bounded_number(payload.get('minimum_rest_hours', existing.get('minimum_rest_hours', '0')), 'minimum rest', 0, 24)
    year_start = str(payload.get('leave_year_start', existing.get('leave_year_start', '01-01')))
    if not re.fullmatch(r'(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])', year_start):
        raise ValueError('Leave year start must be a month and day, such as 04-01.')
    month, day = int(year_start[:2]), int(year_start[3:])
    if not (month == 2 and day == 29):
        try:
            datetime(2023, month, day)
        except ValueError as error:
            raise ValueError('Leave year start must be a real month and day, such as 04-01.') from error
    values = {'contracted_hours': str(contracted), 'rate_of_pay': str(pay), 'standard_shift_minutes': str(duration),
              'work_setup_completed': '1' if complete else '0', 'work_setup_library': json.dumps(list(slots.values())),
              'work_setup_area_slots': json.dumps({str(maps['areas'][item['key']]): [slots[key]['key'] for key in item['slots']] for item in payload['areas']}),
              'leave_allowance_days': str(allowance), 'leave_year_start': f'{month:02d}-{day:02d}', 'minimum_rest_hours': str(rest)}
    connection.executemany('INSERT INTO settings VALUES(?,?) ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value', values.items())
    return {'patterns': len(keep), 'retired': len(set(visible_ids) - keep)}
