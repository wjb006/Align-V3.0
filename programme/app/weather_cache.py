"""Account-scoped durable forecast cache and identified MET Norway fallback."""
import hashlib
import json
import threading
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

FORECAST_LOCK = threading.Lock()


def read(c, key):
    if c is None:
        return None
    row = c.execute('SELECT setting_value FROM settings WHERE setting_key=?', (key,)).fetchone()
    try:
        return json.loads(row[0]) if row else None
    except (ValueError, TypeError):
        return None


def write(c, key, value):
    if c is not None:
        c.execute('INSERT INTO settings(setting_key,setting_value) VALUES(?,?) ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value', (key, json.dumps(value)))


def valid_until(value, now):
    try:
        return datetime.fromisoformat(value) > now
    except (ValueError, TypeError):
        return False


def retry_until(error, now, minutes):
    value = getattr(error, 'retry_after', '')
    response = getattr(error, 'response', None)
    if response is not None: value = response.headers.get('Retry-After', value)
    default = now + timedelta(minutes=minutes)
    try:
        return max(default, now + timedelta(seconds=int(value))).isoformat()
    except (ValueError, TypeError, OverflowError):
        try: return max(default, parsedate_to_datetime(value)).isoformat()
        except (ValueError, TypeError, OverflowError): return default.isoformat()


def code(symbol):
    symbol = symbol.split('_')[0]
    if 'thunder' in symbol: return 95
    if 'snow' in symbol: return 73
    if 'sleet' in symbol: return 69
    if 'rain' in symbol: return 65 if 'heavy' in symbol else 61
    return {'clearsky': 0, 'fair': 1, 'partlycloudy': 2, 'cloudy': 3, 'fog': 45}.get(symbol, -1)


def normalise_met(payload, now):
    zone = ZoneInfo('Europe/London')
    hourly = {key: [] for key in ('time', 'temperature_2m', 'weather_code', 'precipitation_probability', 'wind_speed_10m')}
    groups = {}
    for entry in payload['properties']['timeseries']:
        at = datetime.fromisoformat(entry['time'].replace('Z', '+00:00'))
        if at < now.replace(minute=0, second=0, microsecond=0): continue
        local = at.astimezone(zone)
        data = entry['data']
        instant = data['instant']['details']
        period = data.get('next_1_hours') or data.get('next_6_hours') or {}
        values = (local.isoformat(timespec='minutes')[:16], instant.get('air_temperature'),
                  code(period.get('summary', {}).get('symbol_code', '')),
                  period.get('details', {}).get('probability_of_precipitation'),
                  round(instant['wind_speed'] * 3.6, 1) if instant.get('wind_speed') is not None else None)
        for key, value in zip(hourly, values): hourly[key].append(value)
        groups.setdefault(local.date().isoformat(), []).append(values)
    if not hourly['time']: raise ValueError('The backup forecast is empty.')
    daily = {key: [] for key in ('time', 'temperature_2m_min', 'temperature_2m_max', 'precipitation_probability_max', 'wind_speed_10m_max', 'weather_code')}
    for day, values in list(groups.items())[:7]:
        temperatures = [v[1] for v in values if v[1] is not None]
        rain = [v[3] for v in values if v[3] is not None]
        wind = [v[4] for v in values if v[4] is not None]
        result = (day, min(temperatures) if temperatures else None, max(temperatures) if temperatures else None,
                  max(rain) if rain else None, max(wind) if wind else None, max(v[2] for v in values))
        for key, value in zip(daily, result): daily[key].append(value)
    return {'current': {'time': hourly['time'][0], 'temperature_2m': hourly['temperature_2m'][0], 'weather_code': hourly['weather_code'][0]},
            'hourly': hourly, 'daily': daily, 'source': 'MET Norway',
            'forecast_note': 'Backup forecast. Daily ranges are calculated from available forecast periods; today covers the remaining day. Rain probability may be unavailable.'}


def met_forecast(place, previous=None, now=None):
    import requests
    now = now or datetime.now(timezone.utc)
    headers = {'User-Agent': 'Align/1.3 https://beta.getalign.co.uk', 'Accept': 'application/json'}
    if previous and previous.get('modified'):
        headers['If-Modified-Since'] = previous['modified']
    url = 'https://api.met.no/weatherapi/locationforecast/2.0/compact?' + urlencode({'lat': round(place['latitude'], 2), 'lon': round(place['longitude'], 2)})
    response = requests.get(url, headers=headers, timeout=12)
    if response.status_code == 304 and previous:
        data = previous['data']
    else:
        response.raise_for_status()
        data = normalise_met(response.json(), now)
    expires = now + timedelta(minutes=30)
    try:
        expires = max(expires, parsedate_to_datetime(response.headers['Expires']))
    except (KeyError, ValueError, TypeError):
        pass
    return data, expires.isoformat(), response.headers.get('Last-Modified', (previous or {}).get('modified', ''))


def cached_forecast(c, place, primary, now=None):
    with FORECAST_LOCK:
        result = _cached_forecast(c, place, primary, now)
        return result


def _cached_forecast(c, place, primary, now=None):
    now = now or datetime.now(timezone.utc)
    identity = hashlib.sha256(f"{round(place['latitude'], 2)},{round(place['longitude'], 2)}".encode()).hexdigest()
    # Keep only the latest location per account, so moving around cannot grow storage indefinitely.
    previous = read(c, 'weather_forecast_v1')
    if not previous or previous.get('location') != identity: previous = None
    def result(record, stale=False):
        return {**record['data'], 'checked_at': record['checked_at'], 'stale': stale,
                'retry_at': (read(c, 'weather_retry_v1') or {}).get('until')}
    if previous and valid_until(previous.get('expires'), now): return result(previous)
    retry = read(c, 'weather_retry_v1') or {}
    if valid_until(retry.get('until'), now):
        if previous and valid_until(previous.get('usable_until'), now): return result(previous, True)
        raise ValueError('Weather services are temporarily unavailable. Automatic retry after ' + retry['until'][:16].replace('T', ' ') + ' UTC.')
    try:
        cooldown = read(c, 'weather_primary_retry_v1') or {}
        if valid_until(cooldown.get('until'), now): raise ValueError('Primary provider is cooling down.')
        data = primary()
        data['source'] = 'Open-Meteo'
        expires = (now + timedelta(minutes=30)).isoformat()
        modified = ''
    except ValueError as error:
        # Do not keep retrying a rate-limited provider on each screen refresh.
        if not valid_until(cooldown.get('until'), now):
            write(c, 'weather_primary_retry_v1', {'until': retry_until(error, now, 60)})
        try:
            data, expires, modified = met_forecast(place, previous if previous and previous['data']['source'] == 'MET Norway' else None, now)
        except Exception as error:
            write(c, 'weather_retry_v1', {'until': retry_until(error, now, 30)})
            if previous and valid_until(previous.get('usable_until'), now): return result(previous, True)
            raise ValueError('Both weather services are temporarily unavailable. Please retry later; Align is respecting the provider cooldown.') from None
    record = {'location': identity, 'data': data, 'checked_at': now.isoformat(), 'expires': expires,
              'usable_until': (now + timedelta(hours=24)).isoformat(), 'modified': modified}
    write(c, 'weather_forecast_v1', record)
    write(c, 'weather_retry_v1', {})
    return result(record)
