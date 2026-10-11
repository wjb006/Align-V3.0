"""Private personal planning. External lookups run only on explicit requests."""
import json
import math
import os
import re
from sqlite_support import postgres_enabled
from datetime import datetime, date, time, timedelta, timezone
from urllib.parse import urlparse, parse_qs, urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import ssl
from zoneinfo import ZoneInfo
from display_dates import format_display_datetime

ZONE = ZoneInfo('Europe/London')
MODES = {'drive':'Driving','bus':'Bus','train':'Train','transit':'Bus and train'}
DEFAULTS = dict(travel_modes=['drive', 'bus'], default_travel='drive', show_todos=True,
                include_overdue=True, quick_categories=[], weather_town='', regular_work=False,
                departure_buffer=5, arrival_buffer=10, weather_adjustments=True,
                weather_rain_threshold=50, weather_rain_buffer=10, weather_storm_buffer=15,
                traffic_buffer_cap=30)

def ensure(c):
    if postgres_enabled():
        c.execute('SELECT id, kind, title, due_at, done, created_at, calendar_id, calendar_event_id FROM personal_items LIMIT 0')
        return
    c.execute('''CREATE TABLE IF NOT EXISTS personal_items (
        id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL,
        due_at TEXT NOT NULL DEFAULT '', done INTEGER NOT NULL DEFAULT 0,
        calendar_id TEXT NOT NULL DEFAULT '', calendar_event_id INTEGER,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    columns = {row['name'] for row in c.execute('PRAGMA table_info(personal_items)')}
    if 'calendar_id' not in columns:
        c.execute("ALTER TABLE personal_items ADD COLUMN calendar_id TEXT NOT NULL DEFAULT ''")
    if 'calendar_event_id' not in columns:
        c.execute('ALTER TABLE personal_items ADD COLUMN calendar_event_id INTEGER')

def preferences(c):
    row = c.execute("SELECT setting_value FROM settings WHERE setting_key='personal_preferences'").fetchone()
    return {**DEFAULTS, **(json.loads(row[0]) if row else {})}

def save_preferences(c, body):
    p = preferences(c)
    modes = body.get('travel_modes', p['travel_modes'])
    if not isinstance(modes, list) or not modes or any(m not in MODES for m in modes):
        raise ValueError('Choose your available travel methods.')
    default = body.get('default_travel', p['default_travel'])
    if default not in modes: raise ValueError('The default must be one of your travel methods.')
    categories = body.get('quick_categories', p['quick_categories'])
    if not isinstance(categories, list) or len(categories) > 200 or any(type(x) is not int for x in categories):
        raise ValueError('Choose valid event categories.')
    for key in ('show_todos','include_overdue','regular_work'):
        if key in body:
            if type(body[key]) is not bool: raise ValueError('Choose an on/off preference.')
            p[key] = body[key]
    for key in ('departure_buffer','arrival_buffer'):
        value=int(body.get(key,p[key]))
        if not 0<=value<=120: raise ValueError('Travel buffers must be between 0 and 120 minutes.')
        p[key]=value
    if 'weather_adjustments' in body:
        if type(body['weather_adjustments']) is not bool: raise ValueError('Choose an on/off preference.')
        p['weather_adjustments'] = body['weather_adjustments']
    for key, low, high in (('weather_rain_threshold', 0, 100), ('weather_rain_buffer', 0, 60),
                           ('weather_storm_buffer', 0, 90), ('traffic_buffer_cap', 0, 120)):
        value = int(body.get(key, p[key]))
        if not low <= value <= high: raise ValueError('Weather and traffic buffers are outside the allowed range.')
        p[key] = value
    p.update(travel_modes=list(dict.fromkeys(modes)), default_travel=default,
             quick_categories=list(dict.fromkeys(categories)), weather_town=str(body.get('weather_town',p['weather_town'])).strip()[:120])
    c.execute("INSERT INTO settings VALUES('personal_preferences',?) ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value", (json.dumps(p),))
    return p

def dt(value):
    parsed = datetime.fromisoformat(value)
    return parsed.astimezone(ZONE).replace(tzinfo=None) if parsed.tzinfo else parsed

def events(c, day):
    start = datetime.combine(day,time.min); end = start+timedelta(days=1)
    result = []
    for r in c.execute('''SELECT s.*,COALESCE(NULLIF(l.address,''),s.location_name) AS location,
                                 COALESCE(l.colour,s.colour) AS location_colour, st.colour AS shift_type_colour
                          FROM shifts s
                          LEFT JOIN locations l ON l.id=s.location_id
                          LEFT JOIN shift_types st ON st.id=s.shift_type_id
                          WHERE s.work_date BETWEEN ? AND ?''',((day-timedelta(days=1)).isoformat(),day.isoformat())):
        a=dt(r['work_date']+'T'+r['start_time']); b=dt(r['work_date']+'T'+r['end_time'])
        if b<=a: b+=timedelta(days=1)
        if a<end and b>start:
            result.append(dict(
                id=r['id'], work_date=r['work_date'], start_time=r['start_time'], end_time=r['end_time'],
                start_at=a.isoformat(), end_at=b.isoformat(),
                title=r['location_name']+' · '+r['shift_type_name'], kind='Work', origin='Work',
                all_day=False, location=r['location'] or '', notes=r['notes'] or '',
                category_name=r['shift_type_name'], section_colour=r['location_colour'] or r['colour'],
                location_colour=r['location_colour'] or r['colour'], shift_type_colour=r['shift_type_colour'] or ''))
    for r in c.execute('''SELECT oe.id,oe.section_id,oe.title,oe.start_at,oe.end_at,oe.all_day,oe.location,oe.notes,
                                 os.colour AS section_colour, os.name AS category_name
                          FROM organiser_events oe
                          LEFT JOIN organiser_sections os ON os.id=oe.section_id
                          WHERE oe.start_at < ? AND oe.end_at > ?''', (end.isoformat(),start.isoformat())):
        result.append({**dict(r),'kind':'Event','origin':'Event'})
    for r in c.execute('''SELECT ce.id,cs.section_id,ce.title,ce.start_at,ce.end_at,ce.all_day,ce.location,
                                 '' AS notes, cs.name AS category_name, os.colour AS section_colour
                          FROM calendar_events ce
                          JOIN calendar_sources cs ON cs.id=ce.source_id
                          LEFT JOIN organiser_sections os ON os.id=cs.section_id
                          WHERE ce.start_at < ? AND ce.end_at > ?''', (end.isoformat(),start.isoformat())):
        result.append({**dict(r),'kind':'Event','origin':'Calendar'})
    # A shared calendar may also appear as an imported source: show identical events once.
    unique={(r['start_at'],r['end_at'],r['title']):r for r in result}
    return sorted(unique.values(),key=lambda r:r['start_at'])

def bootstrap(c):
    ensure(c)
    from travel_refresh import synchronize
    pending=synchronize(c)
    c.commit()
    today=datetime.now(ZONE).date()
    return dict(travel_pending=pending, preferences=preferences(c), events=events(c,today), today=today.isoformat(),
                items=[dict(r) for r in c.execute('SELECT * FROM personal_items ORDER BY done,due_at,created_at DESC')],
                routes_configured=True, journey_provider=os.environ.get('ALIGN_JOURNEY_PROVIDER','otp'))

def availability(c, body):
    day=date.fromisoformat(str(body.get('date','')))
    buffer=int(body.get('buffer',0))
    if not 0<=buffer<=240: raise ValueError('Travel allowance must be 0–240 minutes each way.')
    a=datetime.combine(day,time.fromisoformat(body.get('start','08:00')))
    b=datetime.combine(day,time.fromisoformat(body.get('end','22:00')))
    if b<=a: raise ValueError('The availability window must end after it starts.')
    busy=[(dt(r['start_at']),dt(r['end_at'])) for r in events(c,day)]
    if preferences(c)['regular_work']:
        import work_setup
        setup=work_setup.load_setup(c)
        for check in (day-timedelta(days=1),day):
            if c.execute('SELECT 1 FROM annual_leave WHERE leave_date=?',(check.isoformat(),)).fetchone(): continue
            for assignment in setup['assignments']:
                if check.strftime('%A') not in assignment['days']: continue
                slot=next(s for s in setup['slots'] if s['key']==assignment['slot_key'])
                x=datetime.combine(check,time.fromisoformat(slot['start_time']))
                busy.append((x,x+timedelta(minutes=slot['duration_minutes'])))
    delta=timedelta(minutes=buffer)
    now=datetime.now(ZONE).replace(tzinfo=None)
    blocked=sorted((x-delta,y+delta) for x,y in busy)
    merged=[]
    for x,y in blocked:
        if merged and x<=merged[-1][1]: merged[-1]=(merged[-1][0],max(merged[-1][1],y))
        else: merged.append((x,y))
    periods=[]; cursor=max(a,now)
    for x,y in merged:
        if y<=a or x>=b: continue
        x=max(a,x); y=min(b,y)
        if x>cursor: periods.append(dict(start_at=cursor.isoformat(timespec='minutes'),end_at=x.isoformat(timespec='minutes')))
        cursor=max(cursor,y)
    if cursor<b: periods.append(dict(start_at=cursor.isoformat(timespec='minutes'),end_at=b.isoformat(timespec='minutes')))
    return dict(periods=periods, slots=periods, checked_at=datetime.now(ZONE).isoformat(), busy_count=len(busy))

def fetch_json(url, body=None, headers=None):
    request=Request(url, data=json.dumps(body).encode() if body is not None else None,
                    headers={'User-Agent':'Align/149','Content-Type':'application/json',**(headers or {})})
    try:
        with urlopen(request,timeout=18) as response:
            return json.loads(response.read(2000000))
    except HTTPError as error:
        if error.code == 429:
            failure = ValueError('The information provider is rate-limiting requests. Please try again later.')
            failure.retry_after = error.headers.get('Retry-After', '') if error.headers else ''
            raise failure from None
        raise ValueError(f'The information provider returned HTTP {error.code}. Please try again later.') from None
    except URLError as error:
        if isinstance(error.reason, ssl.SSLCertVerificationError):
            raise ValueError('The server could not verify the information provider certificate.') from None
        raise ValueError('The server could not connect to the information provider. Please try again later.') from None
    except Exception:
        raise ValueError('The information service is unavailable. Please try again later.') from None

def weather(c, body=None):
    from weather_cache import read, write, cached_forecast
    body = body or {}
    if 'latitude' in body or 'longitude' in body:
        try:
            lat, lon = float(body['latitude']), float(body['longitude'])
            if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
                raise ValueError()
        except (ValueError, TypeError, KeyError):
            raise ValueError('A valid phone location is required.') from None
        place = dict(name='Near your current location', latitude=round(lat, 2), longitude=round(lon, 2))
    else:
        town = preferences(c)['weather_town']
        if not town: raise ValueError('Allow location access, or set a fallback weather town in Personal preferences.')
        saved = read(c, 'weather_town_location_v1') or {}
        if saved.get('town') == town.casefold():
            place = saved['place']
        else:
            places = fetch_json('https://geocoding-api.open-meteo.com/v1/search?' + urlencode(dict(name=town,count=1,language='en',format='json'))).get('results', [])
            if not places: raise ValueError('Town not found. Try another town name.')
            place = places[0]
            write(c, 'weather_town_location_v1', {'town': town.casefold(), 'place': place})
    forecast = cached_forecast(c, place, lambda: fetch_json('https://api.open-meteo.com/v1/forecast?' + urlencode(dict(
        latitude=place['latitude'], longitude=place['longitude'],
        current='temperature_2m,weather_code',
        hourly='temperature_2m,weather_code,precipitation_probability,wind_speed_10m',
        daily='temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max,weather_code',
        timezone='auto', forecast_days=7,
    ))))
    return dict(
        place=', '.join(filter(None, [place['name'], place.get('admin1'), place.get('country')])),
        current=forecast['current'], hourly=forecast.get('hourly', {}), daily=forecast['daily'],
        checked_at=forecast['checked_at'], source=forecast['source'], stale=forecast.get('stale', False),
        forecast_note=forecast.get('forecast_note', ''), retry_at=forecast.get('retry_at'),
    )


def journey_steps(route, mode):
    result = []
    for leg in route.get('legs', []):
        for step in leg.get('steps', []):
            transit = step.get('transitDetails')
            seconds = float(step.get('staticDuration', '0s').rstrip('s'))
            if transit:
                line = transit.get('transitLine', {})
                vehicle = line.get('vehicle', {}).get('type', '')
                kind = 'bus' if vehicle in ('BUS', 'INTERCITY_BUS', 'TROLLEYBUS') else 'train' if vehicle in ('RAIL', 'COMMUTER_TRAIN', 'HIGH_SPEED_TRAIN', 'LONG_DISTANCE_TRAIN', 'METRO_RAIL', 'SUBWAY', 'TRAM', 'MONORAIL', 'HEAVY_RAIL') else 'transit'
                stops = transit.get('stopDetails', {})
                start, end = stops.get('departureTime'), stops.get('arrivalTime')
                if not seconds and start and end: seconds = max(0, (datetime.fromisoformat(end.replace('Z','+00:00'))-datetime.fromisoformat(start.replace('Z','+00:00'))).total_seconds())
                result.append(dict(mode=kind, minutes=math.ceil(seconds/60), service=line.get('nameShort') or line.get('name',''), start=start, end=end, **{'from':stops.get('departureStop',{}).get('name',''), 'to':stops.get('arrivalStop',{}).get('name','')}))
            else:
                result.append(dict(mode='walk' if step.get('travelMode')=='WALK' else 'drive' if mode=='drive' else 'transit', minutes=math.ceil(seconds/60)))
    return result


def route_plan(route, mode, event_time, departure_buffer, arrival_buffer):
    minutes=math.ceil(float(route['duration'].rstrip('s'))/60)
    target=event_time-timedelta(minutes=arrival_buffer)
    leave=target-timedelta(minutes=minutes+departure_buffer)
    lines=[]; prewalk=0; walking_after=0; first=True; last_arrival=None
    for leg in route.get('legs',[]):
        for step in leg.get('steps',[]):
            t=step.get('transitDetails')
            seconds=float(step.get('staticDuration','0s').rstrip('s'))
            if not t:
                if step.get('travelMode')=='WALK' or mode!='drive':
                    if first: prewalk+=seconds
                    walking_after+=seconds
                    if seconds: lines.append(f"Walk approximately {math.ceil(seconds/60)} minutes")
                continue
            line=t.get('transitLine',{}); stops=t.get('stopDetails',{})
            depart=stops.get('departureTime',''); arrive=stops.get('arrivalTime','')
            if first and depart:
                leave=dt(depart).replace(tzinfo=ZONE)-timedelta(seconds=prewalk,minutes=departure_buffer)
            first=False; walking_after=0
            if arrive: last_arrival=dt(arrive).replace(tzinfo=ZONE)
            def clock(v): return dt(v).strftime('%H:%M') if v else 'time unavailable'
            vehicle=line.get('vehicle',{}).get('name',{}).get('text') or ('Bus' if mode=='bus' else 'Train' if mode=='train' else 'Service')
            lines.append(f"{vehicle} {line.get('nameShort') or line.get('name','')} towards {t.get('headsign','')} · {stops.get('departureStop',{}).get('name','')} {clock(depart)} → {stops.get('arrivalStop',{}).get('name','')} {clock(arrive)}")
    actual_arrival=last_arrival+timedelta(seconds=walking_after) if last_arrival else target
    if actual_arrival>target: return None
    heading=[f"Leave home: {format_display_datetime(leave)}",
             f"Arrive at event location: {actual_arrival.strftime('%H:%M')} · Event: {event_time.strftime('%H:%M')}",
             f"{MODES[mode]} from home · approximately {minutes} minutes travelling",
             f"Allowances: {departure_buffer} minutes before boarding/leaving; arrive {arrival_buffer} minutes before event"]
    footer=['Google Maps · checked '+format_display_datetime(datetime.now(ZONE))+(' · timetable subject to change' if mode!='drive' else ' · driving estimate; check traffic before leaving')]
    return dict(steps=journey_steps(route, mode),minutes=minutes,leave_at=leave.isoformat(timespec='minutes'),arrival_at=actual_arrival.isoformat(timespec='minutes'),walk_to_first_stop_minutes=math.ceil(prewalk/60),notes='\n'.join(heading+lines+footer),mode=mode)


def journey(c, body):
    mode = body.get('mode', preferences(c)['default_travel'])
    if mode == 'drive' and os.environ.get('ALIGN_JOURNEY_PROVIDER', 'otp') == 'here':
        return here_journey(c, body)
    if os.environ.get('ALIGN_JOURNEY_PROVIDER', 'otp') == 'here' or (mode != 'drive' and os.environ.get('ALIGN_HERE_TRANSIT_ENABLED') == '1'):
        from personal_otp import plan
        from here_transit import HERETransitProvider
        result = plan(c, body, preferences(c), HERETransitProvider(), 'HERE')
    elif os.environ.get('ALIGN_JOURNEY_PROVIDER', 'otp') == 'otp':
        from personal_otp import plan
        result = plan(c, body, preferences(c))
    else:
        result = google_journey(c, body)
    return apply_weather_adjustment(c, body, result)


def weather_risk(c, body, event_time):
    prefs = preferences(c)
    if not prefs.get('weather_adjustments', True):
        return 0, {'status': 'disabled', 'extra_minutes': 0}
    try:
        forecast = weather(c, body if 'latitude' in body or 'longitude' in body else {})
        hourly = forecast.get('hourly', {})
        times = hourly.get('time', [])
        index = min(range(len(times)), key=lambda i: abs(
            datetime.fromisoformat(times[i]).replace(tzinfo=ZONE) - event_time
        )) if times else None
        probability = int((hourly.get('precipitation_probability') or [0])[index or 0])
        code = int((hourly.get('weather_code') or [0])[index or 0])
        extra = prefs['weather_storm_buffer'] if code >= 95 else prefs['weather_rain_buffer'] if (
            code in {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82} and probability >= prefs['weather_rain_threshold']
        ) else 0
        return extra, {'status': 'applied' if extra else 'clear', 'extra_minutes': extra,
                       'precipitation_probability': probability, 'weather_code': code,
                       'checked_at': forecast.get('checked_at')}
    except (ValueError, TypeError, KeyError, IndexError, OSError):
        return 0, {'status': 'unavailable', 'extra_minutes': 0}


def apply_weather_adjustment(c, body, result):
    arrival = dt(str(body.get('arrival', ''))).replace(tzinfo=ZONE)
    extra, adjustment = weather_risk(c, body, arrival)
    if not extra:
        result['weather_adjustment'] = adjustment
        return result
    result = {**result}
    result['weather_adjustment'] = adjustment
    shifted = datetime.fromisoformat(result['leave_at']) - timedelta(minutes=extra)
    result['leave_at'] = shifted.isoformat(timespec='minutes')
    if result.get('journeys'):
        result['journeys'] = [{**journey, 'leave_at': (
            datetime.fromisoformat(journey['leave_at']) - timedelta(minutes=extra)
        ).isoformat(timespec='minutes')} for journey in result['journeys']]
    result['notes'] += f"\nWeather allowance: +{extra} minutes for forecast conditions; fixed buffers remain the fallback."
    return result


def here_fetch(url):
    from sqlite_support import postgres_enabled
    if postgres_enabled():
        from here_quota import reserve
        reserve()
    return fetch_json(url)


def here_point(key, value):
    from personal_otp import named_station
    station = named_station(value)
    if station is not None:
        return {'lat': station[0], 'lng': station[1]}
    result = here_fetch('https://geocode.search.hereapi.com/v1/geocode?' + urlencode({'q': value, 'apiKey': key}))
    items = result.get('items') or []
    if not items or not items[0].get('position'):
        raise ValueError('HERE could not locate the journey address.')
    item = items[0]
    score = float((item.get('scoring') or {}).get('queryScore') or 0)
    if not math.isfinite(score) or score < 0.7 or item.get('resultType') in ('locality', 'administrativeArea'):
        raise ValueError('The address match is uncertain. Add the town and postcode, or use a named station.')
    return item['position']


def here_journey(c, body):
    key = os.environ.get('ALIGN_HERE_ROUTING_KEY')
    if not key:
        raise ValueError('HERE routing is not configured; using fixed travel buffers is recommended.')
    prefs = preferences(c)
    depart_after = bool(body.get('departure'))
    arrival = dt(str(body.get('departure') or body.get('arrival', ''))).replace(tzinfo=ZONE)
    target = arrival - timedelta(minutes=int(body.get('arrival_buffer', prefs['arrival_buffer'])))
    if target <= datetime.now(ZONE): raise ValueError('Choose a future event time allowing for early arrival.')
    if 'latitude' in body or 'longitude' in body:
        origin = {'lat': float(body['latitude']), 'lng': float(body['longitude'])}
    elif body.get('origin'):
        origin = here_point(key, str(body['origin']).strip())
    else:
        row = c.execute("SELECT setting_value FROM settings WHERE setting_key='user_address'").fetchone()
        if not row or not row[0].strip(): raise ValueError('Add your home address or allow phone location.')
        origin = here_point(key, row[0].strip())
    destination = str(body.get('destination', '')).strip()[:240]
    if not destination: raise ValueError('Add the event location first.')
    dest = here_point(key, destination)
    response = here_fetch('https://router.hereapi.com/v8/routes?' + urlencode({
        'transportMode': 'car', 'origin': f"{origin['lat']},{origin['lng']}",
        'destination': f"{dest['lat']},{dest['lng']}", 'return': 'summary',
        'departureTime': (target if depart_after else datetime.now(timezone.utc)).isoformat(), 'apiKey': key,
    }))
    summary = ((response.get('routes') or [{}])[0].get('sections') or [{}])[0].get('summary') or {}
    duration = math.ceil(float(summary.get('duration', 0)) / 60)
    if not duration: raise ValueError('HERE did not return a usable driving estimate.')
    traffic_extra = max(0, math.ceil((float(summary.get('duration', 0)) - float(summary.get('baseDuration', summary['duration']))) / 60))
    traffic_extra = min(traffic_extra, prefs['traffic_buffer_cap'])
    weather_extra, adjustment = weather_risk(c, body, arrival)
    total_buffer = int(body.get('departure_buffer', prefs['departure_buffer'])) + traffic_extra + weather_extra
    leave = target if depart_after else target - timedelta(minutes=duration + total_buffer)
    notes = [f"Leave: {format_display_datetime(leave)}", f"Arrive: {leave + timedelta(minutes=duration):%H:%M} · Event: {arrival:%H:%M}",
             f"Driving estimate: {duration} minutes · HERE traffic allowance: +{traffic_extra} minutes",
             f"Fixed departure buffer: {body.get('departure_buffer', prefs['departure_buffer'])} minutes"]
    if weather_extra: notes.append(f"Weather allowance: +{weather_extra} minutes")
    notes.append('HERE Routing · live estimate; check conditions before leaving')
    return {'journeys': [{'minutes': duration, 'leave_at': leave.isoformat(timespec='minutes'),
                          'arrival_at': (leave + timedelta(minutes=duration)).isoformat(timespec='minutes'),
                          'steps': [], 'notes': '\n'.join(notes), 'mode': 'drive', 'provider': 'HERE'}],
            'minutes': duration, 'leave_at': leave.isoformat(timespec='minutes'),
            'arrival_at': (leave + timedelta(minutes=duration)).isoformat(timespec='minutes'),
            'steps': [], 'notes': '\n'.join(notes), 'mode': 'drive', 'provider': 'HERE',
            'traffic_adjustment': {'status': 'applied', 'extra_minutes': traffic_extra},
            'weather_adjustment': adjustment}


def google_journey(c, body):
    key=os.environ.get('ALIGN_GOOGLE_ROUTES_KEY')
    if not key: raise ValueError('Automatic journeys need the owner to configure a Google Routes API key. You can enter travel details manually meanwhile.')
    prefs=preferences(c)
    row=c.execute("SELECT setting_value FROM settings WHERE setting_key='user_address'").fetchone()
    home=row[0].strip() if row else ''
    dest=str(body.get('destination','')).strip()[:240]
    mode=body.get('mode',prefs['default_travel'])
    origin = {'address': home}
    if 'latitude' in body or 'longitude' in body:
        try:
            lat, lon = float(body['latitude']), float(body['longitude'])
            if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180: raise ValueError()
        except (ValueError, TypeError, KeyError):
            raise ValueError('Allow access to a valid phone location to calculate this journey.') from None
        origin = {'location': {'latLng': {'latitude': lat, 'longitude': lon}}}
    elif not home: raise ValueError('Add your home address or allow phone location.')
    if not dest: raise ValueError('Add the event location first.')
    if mode not in MODES: raise ValueError('Choose a travel method.')
    departure_buffer=int(body.get('departure_buffer',prefs['departure_buffer']))
    arrival_buffer=int(body.get('arrival_buffer',prefs['arrival_buffer']))
    if not 0<=departure_buffer<=120 or not 0<=arrival_buffer<=120: raise ValueError('Travel buffers must be between 0 and 120 minutes.')
    arrival=dt(str(body.get('arrival',''))).replace(tzinfo=ZONE)
    target=arrival-timedelta(minutes=arrival_buffer)
    if target<=datetime.now(ZONE): raise ValueError('Choose a future event time allowing for early arrival.')
    request=dict(origin=origin,destination={'address':dest},travelMode='TRANSIT' if mode!='drive' else 'DRIVE',languageCode='en-GB',units='METRIC',computeAlternativeRoutes=True)
    if mode!='drive':
        request.update(arrivalTime=target.astimezone(timezone.utc).isoformat().replace('+00:00','Z'),transitPreferences={'allowedTravelModes':{'bus':['BUS'],'train':['TRAIN'],'transit':['BUS','RAIL']}[mode]})
    mask='routes.duration,routes.legs.steps.transitDetails,routes.legs.steps.staticDuration,routes.legs.steps.travelMode'
    result=fetch_json('https://routes.googleapis.com/directions/v2:computeRoutes',request,{'X-Goog-Api-Key':key,'X-Goog-FieldMask':mask})
    plans=[route_plan(r,mode,arrival,departure_buffer,arrival_buffer) for r in result.get('routes',[])[:4]]
    now=datetime.now(ZONE)
    plans=[r for r in plans if r and datetime.fromisoformat(r['leave_at'])>now]
    if not plans: raise ValueError('No journey is available that leaves now or later and reaches the event in time. Try a different mode or enter travel details manually.')
    if 'latitude' in body:
        for plan in plans:
            plan['notes'] = plan['notes'].replace('Leave home:', 'Leave current location:').replace('from home', 'from current location')
    return {**plans[0],'journeys':plans}


def handle(handler,app,method):
    response_status = 200
    path=urlparse(handler.path).path
    if not path.startswith('/api/personal/'): return False
    try:
        raw = b''
        if method in ('POST','PUT','DELETE'):
            # Drain bounded bodies before rejecting authentication so Windows
            # does not reset the socket and discard the 401/403 response.
            length = int(handler.headers.get('Content-Length','0'))
            if length < 0 or length > 1_000_000:
                handler.close_connection=True
                handler.send_json(413,{'error':'Request is too large.'}); return True
            previous_timeout=handler.connection.gettimeout()
            try:
                handler.connection.settimeout(5)
                raw=handler.rfile.read(length)
            finally: handler.connection.settimeout(previous_timeout)
        if app.BETA_MODE and not handler.require_beta_user(): return True
        if method!='GET':
            if app.BETA_MODE:
                if not handler.beta_same_origin(): return True
            elif handler.headers.get('Origin') not in (None,'http://'+handler.headers.get('Host',''),'https://'+handler.headers.get('Host','')):
                handler.send_json(403,{'error':'Use the current Align site.'}); return True
        body=json.loads(raw or b'{}')
        if not isinstance(body,dict): raise ValueError('Send an object containing the event details.')
        with app.db_connection() as c:
            ensure(c)
            if path=='/api/personal/preferences' and method=='PUT': result=save_preferences(c,body)
            elif path=='/api/personal/availability' and method=='POST': result=availability(c,body)
            elif path=='/api/personal/weather' and method=='POST':
                try:
                    result=weather(c,body)
                except ValueError as error:
                    # Commit only this request's cache/cooldown changes. Weather
                    # helpers must never commit a caller's unrelated planner work.
                    result={'error': str(error)}
                    response_status=400
            elif path=='/api/personal/journey' and method=='POST': result=journey(c,body)
            elif path=='/api/personal/post-event-travel' and method=='POST':
                from post_event_travel import handle as post_travel
                result=post_travel(c,body)
            elif path=='/api/personal/refresh-travel' and method=='POST':
                from travel_refresh import refresh_one
                result=refresh_one(c)
            elif path=='/api/personal/items' and method=='POST':
                rid=str(body.get('id','')); title=str(body.get('title','')).strip(); kind=body.get('kind'); due=str(body.get('due_at',''))
                if not re.fullmatch(r'[a-zA-Z0-9-]{10,80}',rid) or not title or len(title)>2000 or kind not in ('note','reminder'): raise ValueError('Enter a note or reminder of up to 2,000 characters.')
                if due: due=dt(due).isoformat(timespec='minutes')
                calendar_id=str(body.get('calendar_id','')).strip()
                if kind=='reminder' and not due: raise ValueError('Choose a reminder date and time.')
                if kind=='reminder' and calendar_id and not c.execute("SELECT 1 FROM calendar_links WHERE target_kind='icloud_calendar' AND target_key=?",(calendar_id,)).fetchone(): raise ValueError('Choose a calendar from your selected iCloud calendars.')
                old=c.execute('SELECT kind,title,due_at,calendar_id FROM personal_items WHERE id=?',(rid,)).fetchone()
                if old and tuple(old)!=(kind,title,due,calendar_id): raise ValueError('This item was already saved with different details.')
                calendar_event_id = None
                if kind == 'reminder' and calendar_id:
                    from organiser_api import event_section_for_calendar
                    section_id = event_section_for_calendar(c, calendar_id)
                    start = dt(due)
                    c.execute("""INSERT OR IGNORE INTO organiser_events
                        (section_id,title,start_at,end_at,all_day,location,notes,request_id)
                        VALUES(?,?,?,?,0,'','Align reminder',?)""",
                        (section_id, title, start.isoformat(timespec='minutes'),
                         (start + timedelta(minutes=15)).isoformat(timespec='minutes'), 'personal-reminder-' + rid))
                    saved_event = c.execute('SELECT id FROM organiser_events WHERE request_id=?', ('personal-reminder-' + rid,)).fetchone()
                    calendar_event_id = saved_event['id'] if saved_event else None
                c.execute('INSERT OR IGNORE INTO personal_items(id,kind,title,due_at,calendar_id,calendar_event_id) VALUES(?,?,?,?,?,?)',(rid,kind,title,due,calendar_id,calendar_event_id))
                if calendar_event_id:
                    manager=handler.request_icloud_manager(handler.beta_user()) if app.BETA_MODE else app.ICLOUD_MANAGER
                    if manager and manager.enabled: manager.wake.set()
                result={'saved':True}
            elif re.fullmatch('/api/personal/items/[a-zA-Z0-9-]{10,80}',path) and method in ('PUT','DELETE'):
                rid=path.rsplit('/',1)[1]
                if method=='DELETE':
                    item=c.execute('SELECT calendar_event_id FROM personal_items WHERE id=?',(rid,)).fetchone()
                    c.execute('DELETE FROM personal_items WHERE id=?',(rid,))
                    if item and item['calendar_event_id']:
                        c.execute('DELETE FROM organiser_events WHERE id=?',(item['calendar_event_id'],))
                        manager=handler.request_icloud_manager(handler.beta_user()) if app.BETA_MODE else app.ICLOUD_MANAGER
                        if manager and manager.enabled: manager.wake.set()
                else:
                    if type(body.get('done')) is not bool: raise ValueError('Choose complete or incomplete.')
                    c.execute('UPDATE personal_items SET done=? WHERE id=?',(int(body['done']),rid))
                result={'saved':True}
            else:
                handler.send_json(404,{'error':'Not found'}); return True
        handler.send_json(response_status,result)
    except (ValueError,TypeError,KeyError,OverflowError,TimeoutError):
        import sys
        error=sys.exc_info()[1]
        handler.send_json(400,{'error':str(error) if isinstance(error,ValueError) else 'Check the details and try again.'})
    return True
