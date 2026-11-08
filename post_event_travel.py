"""Private per-event onward travel preferences and current destination selection."""
import hashlib
import json
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('Europe/London')


def instant(value):
    value = datetime.fromisoformat(value)
    return value.astimezone(ZONE) if value.tzinfo else value.replace(tzinfo=ZONE)


def events(c):
    """Return retained organiser, imported-calendar and first-class work shifts."""
    result = []
    for kind, table in (('event', 'organiser_events'), ('calendar', 'calendar_events')):
        result.extend(
            {**dict(row), 'kind': kind}
            for row in c.execute(
                f'SELECT id,title,start_at,end_at,all_day,location FROM {table}'
            )
        )
    # Work shifts remain first-class rows. Include them in onward-travel
    # destination selection without copying them into organiser_events.
    import planner_api
    if planner_api._has_table(c, 'shifts'):
        for row in c.execute(
            """SELECT s.id,s.work_date,s.start_time,s.end_time,s.location_name,
                      s.shift_type_name,COALESCE(NULLIF(l.address,''),s.location_name) AS location
               FROM shifts s LEFT JOIN locations l ON l.id=s.location_id"""
        ):
            item = dict(row)
            start = datetime.combine(date.fromisoformat(item['work_date']), time.fromisoformat(item['start_time']))
            end = datetime.combine(date.fromisoformat(item['work_date']), time.fromisoformat(item['end_time']))
            if end <= start:
                end += timedelta(days=1)
            result.append({
                'id': item['id'], 'title': f"{item['location_name']} – {item['shift_type_name']}",
                'start_at': start.isoformat(timespec='minutes'), 'end_at': end.isoformat(timespec='minutes'),
                'all_day': 0, 'location': item['location'] or item['location_name'] or '',
                'kind': 'shift', 'origin': 'Shift',
            })
    return result


def target(c, kind, ident, items=None, home=None):
    items = events(c) if items is None else items
    event = next((e for e in items if e['kind']==kind and e['id']==ident),None)
    if not event: raise ValueError('Event no longer exists.')
    end = instant(event['end_at'])
    origin_key = ' '.join(str(event.get('location') or '').casefold().split())
    norm = lambda e: ' '.join(str(e.get('location') or '').casefold().split())
    # Walk the following located items chronologically. Back-to-back items at the
    # same address extend the stay (and the departure); the first item at a
    # different address within the hour is the destination.
    next_event = None
    while True:
        candidates = sorted((e for e in items if (e['kind'],e['id'])!=(kind,ident) and e['location'].strip() and not e['all_day'] and instant(e['start_at']) <= end+timedelta(hours=1) and (end <= instant(e['start_at']) or (norm(e) == origin_key and instant(e['end_at']) > end))), key=lambda e:(instant(e['start_at']),e['kind'],e['id']))
        if not candidates: break
        first = candidates[0]
        if norm(first) != origin_key:
            next_event = first
            break
        end = max(end, instant(first['end_at']))
        items = [e for e in items if (e['kind'],e['id'])!=(first['kind'],first['id'])]
    if home is None:
        row = c.execute("SELECT setting_value FROM settings WHERE setting_key='user_address'").fetchone()
        home = row[0] if row else ''
    return event, dict(origin=event['location'],destination=next_event['location'] if next_event else home,
                       destination_name=next_event['title'] if next_event else 'Home',departure=end.isoformat(),
                       deadline=next_event['start_at'] if next_event else '',all_day=bool(event['all_day']))


def handle(c, body):
    from personal_planner import preferences
    kind = body.get('kind')
    if kind not in ('event','calendar','shift'): raise ValueError('Choose a saved Align event, imported calendar event or work shift.')
    ident = int(body.get('id',0))
    event, route = target(c,kind,ident)
    key = f'post_event_travel:{kind}:{ident}'
    row = c.execute('SELECT setting_value FROM settings WHERE setting_key=?',(key,)).fetchone()
    saved = json.loads(row[0]) if row else {'enabled':False}
    if 'enabled' in body:
        if type(body['enabled']) is not bool: raise ValueError('Choose whether to show post event travel.')
        saved['enabled'] = body['enabled']
    mode = body.get('mode', saved.get('mode',preferences(c)['default_travel']))
    if mode not in ('drive','bus','train','transit'): raise ValueError('Choose a travel mode.')
    route['mode'] = saved['mode'] = mode
    fingerprint = hashlib.sha256(json.dumps(route,sort_keys=True).encode()).hexdigest()
    if saved.get('fingerprint') != fingerprint:
        saved.pop('journey',None)
    result = {**route,'enabled':saved['enabled'],'journey':saved.get('journey')}
    if saved['enabled'] and body.get('plan'):
        try:
            if route['all_day']: raise ValueError('Set an event end time to plan travel after it.')
            if not route['origin'].strip(): raise ValueError('Add an event location first.')
            if not route['destination'].strip(): raise ValueError('Add your home address in Personal details.')
            if instant(route['departure']) <= datetime.now(ZONE):
                # A completed event must never trigger a retrospective route
                # calculation. Keep the journey that was planned before it
                # finished, provided its saved inputs still match this route.
                result['journey'] = saved.get('journey')
                result['historical'] = bool(result['journey'])
                if result['journey']:
                    result['message'] = 'This event has finished; its previously planned return journey is being retained.'
                else:
                    result['error'] = 'This event has finished. A new departure recommendation cannot be generated retrospectively.'
            else:
                journey = plan(c,route)
                saved.update(journey=journey,fingerprint=fingerprint)
                result['journey'] = journey
        except ValueError as error:
            # Provider errors should not erase a still-valid saved itinerary.
            result.update(journey=saved.get('journey'),error=str(error))
    c.execute('INSERT INTO settings(setting_key,setting_value) VALUES(?,?) ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value',(key,json.dumps(saved)))
    return result


def plan(c, route):
    from personal_planner import here_journey, preferences
    from personal_otp import plan as transit_plan
    import os
    body = dict(origin=route['origin'],destination=route['destination'],departure=route['departure'],
                arrival=route['departure'],mode=route['mode'],departure_buffer=0,arrival_buffer=0)
    if route['mode']=='drive':
        result = here_journey(c,body)
    else:
        if os.environ.get('ALIGN_JOURNEY_PROVIDER')=='here' or os.environ.get('ALIGN_HERE_TRANSIT_ENABLED')=='1':
            from here_transit import HERETransitProvider
            result = transit_plan(c,body,preferences(c),HERETransitProvider(),'HERE')
        else: result = transit_plan(c,body,preferences(c))
    journeys = result.get('journeys') or [result]
    usable = [j for j in journeys if instant(j['leave_at'])>=instant(route['departure']) and (not route['deadline'] or instant(j['arrival_at'])<=instant(route['deadline']))]
    if not usable: raise ValueError('No journey can leave after this event and reach the next event in time.')
    return min(usable,key=lambda j:instant(j['arrival_at']))


def decorate(c, items, kind=None):
    saved_rows = {row[0]:json.loads(row[1]) for row in c.execute("SELECT setting_key,setting_value FROM settings WHERE setting_key LIKE 'post_event_travel:%'")}
    all_events = None
    home_row = None
    for item in items:
        event_kind = kind or ('calendar' if item.get('origin')=='Calendar' or item.get('source_kind')=='icloud' else 'event')
        saved = saved_rows.get(f"post_event_travel:{event_kind}:{item['id']}",{})
        # Automatic travel is part of the daily timeline for every dated event.
        # Keep any saved route/mode, but don't let legacy per-event False values
        # suppress travel on the current V3 experience.
        if all_events is None:
            all_events = events(c)
            home_row = c.execute("SELECT setting_value FROM settings WHERE setting_key='user_address'").fetchone()
        _, route = target(c,event_kind,item['id'],all_events,home_row[0] if home_row else '')
        from personal_planner import preferences
        route['mode'] = saved.get('mode') or preferences(c)['default_travel']
        fingerprint = hashlib.sha256(json.dumps(route,sort_keys=True).encode()).hexdigest()
        item['post_travel'] = {**route,'enabled':True,'historical':instant(route['departure']) <= datetime.now(ZONE),'journey':saved.get('journey') if saved.get('fingerprint')==fingerprint else None}
    return items
