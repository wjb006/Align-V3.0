"""Event journeys using the installed OpenTripPlanner graph; no Google key.

EASY TO EDIT: postcode resolution deliberately uses a public postcode centre.
For precise origins choose phone location. Local station names resolve locally.
"""
import json
import math
import re
from datetime import datetime, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo
from display_dates import format_display_datetime
from align_paths import bundled_file
from transport_providers import OTPProvider, ProviderUnavailable, request_json

ZONE = ZoneInfo('Europe/London')
MAX_JOURNEYS = 4
MODE_MAP = {'bus':['walk','bus'], 'train':['walk','rail'], 'transit':['walk','bus','rail']}


def named_station(address):
    name = str(address or '').split(',')[0].strip().casefold()
    name = re.sub(r'\s+(?:(?:railway|rail|train)\s+)?station$', '', name)
    stops = json.loads(bundled_file('merseyside_stops.json').read_text(encoding='utf-8'))
    matches = [s for s in stops if s['name'].casefold() == name]
    points = {tuple(s['point']) for s in matches}
    return points.pop() if len(points) == 1 else None


def resolve_place(address):
    address = str(address or '').strip()
    station = named_station(address)
    if station is not None: return station, 'named stop or station'
    codes = re.findall(r'\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b', address.upper())
    if codes:
        postcode = codes[-1]
        data = request_json('https://api.postcodes.io/postcodes/' + quote(postcode))
        point = data.get('result')
        if not point: raise ValueError('Postcode not found. Check the full postcode.')
        return (point['latitude'], point['longitude']), 'postcode centre (approximate)'
    stops = json.loads(bundled_file('merseyside_stops.json').read_text(encoding='utf-8'))
    matches = [s for s in stops if s['name'].casefold() == address.casefold()]
    points = {tuple(s['point']) for s in matches}
    if len(points) == 1: return points.pop(), 'named stop or station'
    raise ValueError('Include a full UK postcode in your home/event address, or use an exact local station name.')


def resolve_journey_place(address, provider_name):
    try:
        return resolve_place(address)
    except ValueError:
        if provider_name != 'HERE':
            raise
    import os
    from personal_planner import here_point
    key = os.environ.get('ALIGN_HERE_ROUTING_KEY')
    if not key:
        raise ValueError('HERE address lookup is not configured.')
    point = here_point(key, str(address).strip()[:240])
    lat, lon = float(point['lat']), float(point['lng'])
    if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError('HERE returned an invalid location.')
    return (lat, lon), 'HERE address lookup'


def plan(c, body, prefs, provider=None, provider_name='OpenTripPlanner'):
    mode = body.get('mode', prefs['default_travel'])
    if mode not in MODE_MAP:
        raise ValueError('Choose Bus, Train or Bus and train for OpenTripPlanner. Use Apple Maps for driving.')
    departure_buffer = int(body.get('departure_buffer', prefs['departure_buffer']))
    arrival_buffer = int(body.get('arrival_buffer', prefs['arrival_buffer']))
    if not 0 <= departure_buffer <= 120 or not 0 <= arrival_buffer <= 120:
        raise ValueError('Travel buffers must be between 0 and 120 minutes.')
    depart_after = bool(body.get('departure'))
    arrival = datetime.fromisoformat(str(body.get('departure') or body.get('arrival','')))
    arrival = arrival.astimezone(ZONE) if arrival.tzinfo else arrival.replace(tzinfo=ZONE)
    target = arrival - timedelta(minutes=arrival_buffer)
    now = datetime.now(ZONE)
    if target <= now: raise ValueError('Choose a future event time allowing for early arrival.')
    destination = str(body.get('destination','')).strip()[:240]
    if not destination: raise ValueError('Add an event location with a full postcode.')
    try:
        if 'latitude' in body or 'longitude' in body:
            try:
                lat, lon = float(body['latitude']), float(body['longitude'])
                if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180: raise ValueError()
            except (ValueError,TypeError,KeyError): raise ValueError('A valid phone location is required.') from None
            origin, origin_note, origin_name = (lat,lon), 'phone location', 'current location'
        elif body.get('origin'):
            origin, origin_note = resolve_journey_place(str(body['origin']), provider_name)
            origin_name = 'event'
        else:
            row = c.execute("SELECT setting_value FROM settings WHERE setting_key='user_address'").fetchone()
            home = row[0] if row else ''
            if not home: raise ValueError('Add your home address and full postcode in Personal details.')
            origin, origin_note = resolve_journey_place(home, provider_name)
            origin_name = 'home'
        dest, dest_note = resolve_journey_place(destination, provider_name)
        planner = provider or OTPProvider()
        candidates = planner.plan(origin, dest, target, MODE_MAP[mode], depart_after=True) if depart_after else planner.plan(origin, dest, target, MODE_MAP[mode])
    except ProviderUnavailable:
        if provider_name == 'HERE':
            raise ValueError('HERE transit is unavailable or its quota has been reached. Try again later or enter travel details manually.') from None
        raise ValueError('OpenTripPlanner or postcode lookup is unavailable. Start Align with Start Align Merseyside.bat and retry.') from None
    plans = []
    for candidate in candidates:
        legs = candidate.get('legs', [])
        if not legs or any(l['mode'] not in MODE_MAP[mode] for l in legs): continue
        start = datetime.fromisoformat(legs[0]['start']).astimezone(ZONE)
        end = datetime.fromisoformat(legs[-1]['end']).astimezone(ZONE)
        leave = start - timedelta(minutes=departure_buffer)
        if leave <= now or end < start: continue
        if (depart_after and leave < target) or (not depart_after and end > target): continue
        steps = []
        previous_end = None
        for leg in legs:
            a = datetime.fromisoformat(leg['start']).astimezone(ZONE)
            b = datetime.fromisoformat(leg['end']).astimezone(ZONE)
            if previous_end and a > previous_end:
                steps.append(dict(mode='wait',minutes=math.ceil((a-previous_end).total_seconds()/60),start=previous_end.isoformat(),end=a.isoformat(),service='Connection'))
            steps.append({**leg,'mode':'train' if leg['mode']=='rail' else leg['mode'], 'minutes':math.ceil((b-a).total_seconds()/60)})
            previous_end = b
        minutes = math.ceil((end-start).total_seconds()/60)
        notes = [f"Leave {origin_name}: {format_display_datetime(leave)}", f"Arrive: {end:%H:%M}" + (f" · Event ends: {arrival:%H:%M}" if depart_after else f" · Event: {arrival:%H:%M}"), f"{minutes} minutes including walking and connections", f"Allowances: {departure_buffer} minutes before leaving; arrive {arrival_buffer} minutes early", f"Start: {origin_note}; destination: {dest_note}"]
        for step in steps:
            a = datetime.fromisoformat(step['start']).astimezone(ZONE)
            notes.append(f"{step['mode'].title()} {step.get('service','')} · {step['minutes']} min · {a:%H:%M} · {step.get('from','')} → {step.get('to','')}")
        notes.append(provider_name + ' · scheduled times; live delay updates unavailable · checked '+format_display_datetime(now))
        notes.extend(candidate.get('attributions', []))
        plans.append(dict(minutes=minutes,leave_at=leave.isoformat(timespec='minutes'),arrival_at=end.isoformat(timespec='minutes'),steps=steps,notes='\n'.join(notes),mode=mode,provider=provider_name,scheduled=True))
    plans.sort(key=lambda p: (datetime.fromisoformat(p['arrival_at']).timestamp() if depart_after else -datetime.fromisoformat(p['leave_at']).timestamp(), p['minutes']))
    if not plans: raise ValueError('No scheduled journey reaches this event in time. Try another time or travel mode; check that the timetable covers this date.')
    plans = plans[:MAX_JOURNEYS]
    return {**plans[0], 'journeys':plans}
