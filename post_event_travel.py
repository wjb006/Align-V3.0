"""Private per-event onward travel preferences and current destination selection."""
import hashlib
import json
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('Europe/London')
TIMELINE_CACHE_VERSION = 2


def instant(value):
    value = datetime.fromisoformat(value)
    return value.astimezone(ZONE) if value.tzinfo else value.replace(tzinfo=ZONE)


def _location_keys(event):
    keys = []
    location_id = event.get('location_id')
    if location_id not in (None, ''):
        keys.append(('id', str(location_id)))
    try:
        latitude = float(event.get('latitude', event.get('location_latitude')))
        longitude = float(event.get('longitude', event.get('location_longitude')))
        if -90 <= latitude <= 90 and -180 <= longitude <= 180:
            keys.append(('coordinates', f'{latitude:.5f},{longitude:.5f}'))
    except (TypeError, ValueError):
        pass
    address = ' '.join(str(event.get('location') or event.get('address') or '').casefold().split())
    if address:
        keys.append(('address', address))
    return keys


def _same_location(first, second):
    return bool(set(_location_keys(first)) & set(_location_keys(second)))


def _provider_cache_version(mode):
    import os
    provider = os.environ.get('ALIGN_JOURNEY_PROVIDER', 'otp')
    if mode == 'drive':
        name = 'here-routing'
    elif provider == 'here' or os.environ.get('ALIGN_HERE_TRANSIT_ENABLED') == '1':
        name = 'here-transit'
    elif provider == 'otp':
        name = 'open-trip-planner'
    else:
        name = 'google-routes'
    endpoint = os.environ.get('ALIGN_OTP_URL', '') if name == 'open-trip-planner' else ''
    return hashlib.sha256(json.dumps([name, endpoint, TIMELINE_CACHE_VERSION]).encode()).hexdigest()


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
            """SELECT s.id,s.work_date,s.start_time,s.end_time,s.location_id,s.location_name,
                      s.shift_type_name,l.address AS location
               FROM shifts s LEFT JOIN locations l ON l.id=s.location_id"""
        ):
            item = dict(row)
            start = datetime.combine(date.fromisoformat(item['work_date']), time.fromisoformat(item['start_time']))
            end = datetime.combine(date.fromisoformat(item['work_date']), time.fromisoformat(item['end_time']))
            if end <= start:
                end += timedelta(days=1)
            result.append({
                'id': item['id'], 'location_id': item.get('location_id'),
                'title': f"{item['location_name']} – {item['shift_type_name']}",
                'start_at': start.isoformat(timespec='minutes'), 'end_at': end.isoformat(timespec='minutes'),
                'all_day': 0, 'location': item.get('location') or '',
                'kind': 'shift', 'origin': 'Shift',
            })
    return result


def target(c, kind, ident, items=None, home=None, timeline=False):
    items = events(c) if items is None else items
    event = next((e for e in items if e['kind']==kind and e['id']==ident),None)
    if not event: raise ValueError('Event no longer exists.')
    end = instant(event['end_at'])
    event_day = str(event['start_at'])[:10]
    # Walk the following located items chronologically. Back-to-back items at the
    # same address extend the stay (and the departure); the first item at a
    # different address within the hour is the destination.
    next_event = None
    while True:
        candidates = sorted((e for e in items if (e['kind'],e['id'])!=(kind,ident) and str(e.get('location') or '').strip() and not e['all_day'] and
            (str(e['start_at'])[:10] == event_day if timeline else instant(e['start_at']) <= end+timedelta(hours=1)) and
            (end <= instant(e['start_at']) or (_same_location(e, event) and instant(e['end_at']) > end))),
            key=lambda e:(instant(e['start_at']),e['kind'],e['id']))
        if not candidates: break
        first = candidates[0]
        if not _same_location(first, event):
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
    timeline = body.get('timeline', False)
    if type(timeline) is not bool: raise ValueError('Choose a valid daily timeline travel request.')
    event, route = target(c,kind,ident,timeline=timeline)
    if timeline:
        from personal_planner import preferences
        route.update(timeline=True, arrival_buffer=int(preferences(c)['arrival_buffer']))
    key = f'post_event_travel:{"timeline:" if timeline else ""}{kind}:{ident}'
    row = c.execute('SELECT setting_value FROM settings WHERE setting_key=?',(key,)).fetchone()
    saved = json.loads(row[0]) if row else {'enabled':False}
    if 'enabled' in body:
        if type(body['enabled']) is not bool: raise ValueError('Choose whether to show post event travel.')
        saved['enabled'] = body['enabled']
    mode = body.get('mode', saved.get('mode',preferences(c)['default_travel']))
    if mode not in ('drive','bus','train','transit'): raise ValueError('Choose a travel mode.')
    route['mode'] = saved['mode'] = mode
    fingerprint_data = {'route':route,'provider_version':_provider_cache_version(mode)} if timeline else route
    fingerprint = hashlib.sha256(json.dumps(fingerprint_data,sort_keys=True).encode()).hexdigest()
    if saved.get('fingerprint') != fingerprint:
        saved.pop('journey',None)
    result = {**route,'enabled':saved['enabled'],'journey':saved.get('journey')}
    if saved['enabled'] and body.get('plan'):
        if timeline and saved.get('fingerprint') == fingerprint and saved.get('journey'):
            result['journey'] = saved['journey']
            result['historical'] = instant(route['departure']) <= datetime.now(ZONE)
        else:
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
    arrival_buffer = int(route.get('arrival_buffer', 0)) if route.get('timeline') else 0
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
    latest_arrival = instant(route['deadline'])-timedelta(minutes=arrival_buffer) if route.get('deadline') else None
    usable = [j for j in journeys if instant(j['leave_at'])>=instant(route['departure']) and (latest_arrival is None or instant(j['arrival_at'])<=latest_arrival)]
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
