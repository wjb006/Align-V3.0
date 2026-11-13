"""Stop proximity and live-delay lookups.

Routes, bus numbers and walking times always come from a configured provider.
This module only decides which published stops are close enough to use, and
how many minutes a configured live feed says a matched service is running late.
Nothing here invents a route, a service number or a duration.
"""
from __future__ import annotations

import json
import os
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from align_paths import bundled_file

WALK_METRES_PER_MINUTE = 80
AREA_PAD_METRES = 180
CACHE_SECONDS = 12 * 60 * 60
_CACHE_LOCK = threading.Lock()
_AREA_CACHE: dict[str, tuple[float, list]] = {}
_AREAS = None

RAIL_STOPS = {'RLY', 'RPL', 'MET', 'PLT'}
BUS_STOPS = {'BCT', 'BCS', 'BCQ', 'BST', 'MKD', 'CUS'}


def _areas():
    global _AREAS
    if _AREAS is None:
        _AREAS = json.loads(bundled_file('naptan_areas.json').read_text(encoding='utf-8'))
    return _AREAS


def area_codes(origin):
    """ATCO area codes whose published gazetteer box contains this point."""
    lat, lon = origin
    hits = [area for area in _areas()
            if area['south'] <= lat <= area['north'] and area['west'] <= lon <= area['east']]
    hits.sort(key=lambda area: (area['north'] - area['south']) * (area['east'] - area['west']))
    return [area['atco'] for area in hits[:2]]


def _mode(stop_type):
    if stop_type in RAIL_STOPS:
        return 'rail'
    if stop_type in BUS_STOPS:
        return 'bus'
    return ''


def _rows_to_stops(rows, origin):
    from transport_providers import distance
    stops = []
    for row in rows:
        mode = _mode(str(row.get('StopType') or ''))
        if not mode:
            continue
        if str(row.get('Status') or 'active').casefold() not in ('', 'active'):
            continue
        try:
            point = (float(row['Latitude']), float(row['Longitude']))
        except (KeyError, TypeError, ValueError):
            continue
        metres = distance(origin, point)
        limit = 2500 if mode == 'rail' else 1200
        if metres > limit:
            continue
        stops.append({
            'id': row.get('ATCOCode') or '',
            'name': row.get('CommonName') or '',
            'mode': mode,
            'metres': round(metres),
            'lat': point[0],
            'lon': point[1],
        })
    stops.sort(key=lambda stop: (stop['metres'], stop['id']))
    return stops


def _fetch_bytes(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https':
        raise OSError('NaPTAN requires HTTPS')
    request = Request(url, headers={'User-Agent': 'Align/158'})
    with urlopen(request, timeout=20) as response:
        data = response.read(8_000_001)
    if len(data) > 8_000_000:
        raise OSError('NaPTAN extract is too large')
    return data


def _area_stops(code, fetch):
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _AREA_CACHE.get(code)
        if cached and now - cached[0] < CACHE_SECONDS:
            return cached[1]
    import csv
    from io import StringIO
    base = os.environ.get('ALIGN_NAPTAN_API_URL', 'https://naptan.api.dft.gov.uk/v1/access-nodes').rstrip('/')
    url = f'{base}?dataFormat=csv&atcoAreaCodes={quote(code)}'
    try:
        text = fetch(url).decode('utf-8-sig', errors='replace')
        rows = list(csv.DictReader(StringIO(text)))
    except Exception:
        return []
    with _CACHE_LOCK:
        _AREA_CACHE[code] = (now, rows)
    return rows


def nearby_stops(origin, fetch=None):
    """Stops from a local NaPTAN file, or the public API when explicitly enabled.

    An empty list means the check could not be made. Callers then keep the
    provider journey instead of inventing a nearer stop.
    """
    from transport_providers import NaptanProvider
    csv_stops = NaptanProvider().nearby(origin) if os.environ.get('ALIGN_NAPTAN_CSV') else []
    if csv_stops:
        return csv_stops
    if os.environ.get('ALIGN_NAPTAN_LIVE') != '1':
        return []
    fetch = fetch or _fetch_bytes
    rows = []
    for code in area_codes(origin):
        rows.extend(_area_stops(code, fetch))
    return _rows_to_stops(rows, origin)[:12]


def access_cap_metres(stops, modes):
    """Walk cap from the nearest published stop, plus a short margin.

    The margin lets the router reach that stop. It does not extend the walk
    out to a much further stop when a closer one exists.
    """
    wanted = {mode for mode in modes if mode in ('bus', 'rail')}
    relevant = [stop for stop in stops if stop['mode'] in wanted]
    if not relevant:
        return None
    nearest = min(stop['metres'] for stop in relevant)
    return min(2000, max(200, nearest + AREA_PAD_METRES))


def _walk_minutes(leg):
    if leg.get('minutes') is not None:
        try:
            return float(leg['minutes'])
        except (TypeError, ValueError):
            return None
    try:
        start = datetime.fromisoformat(str(leg['start']))
        end = datetime.fromisoformat(str(leg['end']))
    except (KeyError, TypeError, ValueError):
        return None
    return max(0, (end - start).total_seconds() / 60)


def prefer_closer_boarding(journeys, stops, modes):
    """Drop itineraries whose first walk goes far past a closer published stop."""
    cap = access_cap_metres(stops, modes)
    if cap is None:
        return list(journeys), 0
    kept = []
    dropped = 0
    for journey in journeys:
        legs = journey.get('legs') or []
        if not legs or legs[0].get('mode') != 'walk':
            kept.append(journey)
            continue
        minutes = _walk_minutes(legs[0])
        if minutes is None:
            kept.append(journey)
            continue
        implied = minutes * WALK_METRES_PER_MINUTE
        if implied > cap + 120:
            dropped += 1
            continue
        kept.append(journey)
    return kept, dropped


def _names_match(left, right):
    a = ' '.join(str(left or '').casefold().split())
    b = ' '.join(str(right or '').casefold().split())
    if len(a) < 4 or len(b) < 4:
        return False
    return a in b or b in a


def _local(tag):
    return tag.rsplit('}', 1)[-1]


def _child_text(node, name):
    for child in list(node):
        if _local(child.tag) == name and child.text:
            return child.text.strip()
    return ''


def parse_bods_delay(payload, service, stop_name):
    """Minutes late for one line at one stop. None when the feed is ambiguous."""
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return None
    wanted = str(service or '').strip()
    found = []
    for journey in root.iter():
        if _local(journey.tag) != 'MonitoredVehicleJourney':
            continue
        line = _child_text(journey, 'PublishedLineName') or _child_text(journey, 'LineRef')
        if line != wanted:
            continue
        for call in journey.iter():
            if _local(call.tag) not in ('MonitoredCall', 'PreviousCall', 'OnwardCall'):
                continue
            if not _names_match(_child_text(call, 'StopPointName'), stop_name):
                continue
            aimed = _child_text(call, 'AimedDepartureTime') or _child_text(call, 'AimedArrivalTime')
            expected = _child_text(call, 'ExpectedDepartureTime') or _child_text(call, 'ExpectedArrivalTime')
            if not aimed or not expected:
                continue
            try:
                delay = round((datetime.fromisoformat(expected.replace('Z', '+00:00'))
                               - datetime.fromisoformat(aimed.replace('Z', '+00:00'))).total_seconds() / 60)
            except ValueError:
                continue
            found.append(delay)
    unique = set(found)
    if len(unique) == 1:
        return found[0]
    return None


def _crs(name):
    import re
    match = re.search(r'\(([A-Z]{3})\)\s*$', str(name or '').strip())
    return match.group(1) if match else ''


def parse_darwin_delay(payload, service, stop_name, when):
    """Minutes late from an OpenLDBWS board. None when no single service matches."""
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return None
    target = when.astimezone(timezone.utc) if isinstance(when, datetime) else None
    clock = target.strftime('%H:%M') if target else ''
    wanted = str(service or '').strip().casefold()
    found = []
    for service_node in root.iter():
        if _local(service_node.tag) != 'service':
            continue
        std = _child_text(service_node, 'std') or _child_text(service_node, 'sta')
        etd = _child_text(service_node, 'etd') or _child_text(service_node, 'eta')
        destination = ''
        for child in service_node.iter():
            if _local(child.tag) == 'destination':
                destination = ''.join(part.text or '' for part in child.iter() if _local(part.tag) == 'locationName')
                break
        headcode = (_child_text(service_node, 'trainid') or _child_text(service_node, 'serviceID')).casefold()
        operator = _child_text(service_node, 'operator').casefold()
        identity = wanted and (wanted == headcode or wanted in operator or wanted in destination.casefold())
        time_match = bool(clock) and std == clock
        place_match = _names_match(destination, stop_name) or _names_match(destination, service)
        if not (time_match or identity or place_match):
            continue
        if not time_match and not identity:
            continue
        if etd.casefold() in ('on time', 'starts here', 'no report'):
            found.append(0)
        elif etd.casefold() in ('delayed', 'cancelled', ''):
            continue
        else:
            try:
                hours, minutes = etd.split(':')
                scheduled_h, scheduled_m = std.split(':')
                found.append((int(hours) * 60 + int(minutes)) - (int(scheduled_h) * 60 + int(scheduled_m)))
            except (ValueError, AttributeError):
                continue
    unique = set(found)
    if len(unique) == 1:
        return found[0]
    return None


def _bods_configured():
    return bool(os.environ.get('ALIGN_BODS_API_KEY', '').strip()
                or (os.environ.get('ALIGN_BODS_LIVE_URL') and os.environ.get('ALIGN_BODS_TOKEN')))


def _darwin_configured():
    return bool(os.environ.get('ALIGN_DARWIN_TOKEN', '').strip()
                or (os.environ.get('ALIGN_DARWIN_LIVE_URL') and os.environ.get('ALIGN_DARWIN_TOKEN')))


def bods_delay(service, stop_name, fetch=None):
    key = os.environ.get('ALIGN_BODS_API_KEY', '').strip()
    if not key or not service or not stop_name:
        return None
    fetch = fetch or _fetch_bytes
    base = os.environ.get('ALIGN_BODS_API_URL', 'https://data.bus-data.dft.gov.uk/api/v1/datafeed').rstrip('/')
    url = f'{base}?lineRef={quote(str(service))}&api_key={quote(key)}'
    try:
        payload = fetch(url)
    except Exception:
        return None
    return parse_bods_delay(payload, service, stop_name)


def darwin_delay(service, from_name, to_name, when, fetch=None):
    token = os.environ.get('ALIGN_DARWIN_TOKEN', '').strip()
    crs = _crs(from_name)
    if not token or not crs:
        return None
    fetch = fetch or _post_xml
    body = f'''<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ldb="http://thalesgroup.com/RTTI/2017-10-01/ldb/" xmlns:typ="http://thalesgroup.com/RTTI/2013-11-28/Token/types">
  <soap:Header><typ:AccessToken><typ:TokenValue>{_xml(token)}</typ:TokenValue></typ:AccessToken></soap:Header>
  <soap:Body><ldb:GetDepartureBoardRequest><ldb:numRows>12</ldb:numRows><ldb:crs>{crs}</ldb:crs></ldb:GetDepartureBoardRequest></soap:Body>
</soap:Envelope>'''
    try:
        payload = fetch('https://lite.realtime.nationalrail.co.uk/OpenLDBWS/ldb11.asmx', body)
    except Exception:
        return None
    return parse_darwin_delay(payload, service, to_name, when)


def _xml(value):
    return (str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def _post_xml(url, body):
    parsed = urlparse(url)
    if parsed.scheme != 'https':
        raise OSError('Darwin requires HTTPS')
    request = Request(url, data=body.encode(), headers={
        'Content-Type': 'text/xml; charset=utf-8',
        'User-Agent': 'Align/158',
    })
    with urlopen(request, timeout=8) as response:
        data = response.read(2_000_001)
    if len(data) > 2_000_000:
        raise OSError('Darwin response is too large')
    return data


def service_delay(leg, fetch=None):
    """Delay in minutes for one leg, from a configured feed only."""
    mode = leg.get('mode')
    if mode == 'bus' and os.environ.get('ALIGN_BODS_API_KEY', '').strip():
        return bods_delay(leg.get('service') or leg.get('service_number'), leg.get('from'), fetch)
    if mode in ('rail', 'train') and os.environ.get('ALIGN_DARWIN_TOKEN', '').strip():
        when = None
        try:
            when = datetime.fromisoformat(str(leg.get('start')))
        except (TypeError, ValueError):
            when = None
        return darwin_delay(leg.get('service') or '', leg.get('from') or '', leg.get('to') or '', when, fetch)
    return None


def live_sources():
    return {
        'otp': bool(os.environ.get('ALIGN_OTP_URL', '').strip()),
        'naptan': bool(os.environ.get('ALIGN_NAPTAN_CSV') or os.environ.get('ALIGN_NAPTAN_LIVE') == '1'),
        'bods': _bods_configured(),
        'darwin': _darwin_configured(),
    }


def hosted_otp_url():
    """A non-loopback OTP endpoint. Loopback stays a local-only server."""
    url = os.environ.get('ALIGN_OTP_URL', '').strip()
    host = (urlparse(url).hostname or '').rstrip('.').casefold() if url else ''
    if host in ('', 'localhost', '127.0.0.1', '::1'):
        return ''
    return url
