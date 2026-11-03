"""Account-private arrive-by planning. Current origins never enter persistence."""
import transport_places
import copy
from datetime import datetime, timedelta, timezone
import json
import math
import os
import re
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
from transport_providers import OTPProvider, NaptanProvider, StatusHook, ProviderUnavailable
from transport_ranking import rank, timestamp

def validate_hosted_storage(c):
    """Validate explicitly provisioned Travel tables; never mutate hosted schema."""
    c.execute('SELECT id, arrival_buffer, modes, home_lat, home_lon FROM transport_preferences LIMIT 0')
    c.execute('SELECT event_key, payload, updated_at, expires_at FROM transport_journey_cache LIMIT 0')

def enabled(): return os.environ.get('ALIGN_TRANSPORT_ENABLED','0')=='1'

def routing_status():
    here = os.environ.get('ALIGN_JOURNEY_PROVIDER') == 'here'
    configured = bool(os.environ.get('ALIGN_HERE_ROUTING_KEY') and
                      os.environ.get('ALIGN_HERE_TRANSIT_ENABLED') == '1') if here else bool(os.environ.get('ALIGN_OTP_URL'))
    return {'provider': 'HERE' if here else 'OpenTripPlanner', 'routing_configured': configured}

def coordinates(value):
    if not isinstance(value,(list,tuple)) or len(value)!=2: raise ValueError('Enter latitude and longitude')
    lat,lon=map(float,value)
    if not math.isfinite(lat) or not math.isfinite(lon) or not -90<=lat<=90 or not -180<=lon<=180: raise ValueError('Invalid coordinates')
    return lat,lon

def preferences(c):
    row=c.execute('SELECT arrival_buffer,modes,home_lat,home_lon FROM transport_preferences WHERE id=1').fetchone()
    return {'arrival_buffer':row[0],'modes':json.loads(row[1]),'home':list(row[2:]) if row[2] is not None else None}

def save_preferences(c, body):
    buffer=body.get('arrival_buffer',10)
    modes=body.get('modes',['bus','rail','walk'])
    if type(buffer)!=int or not 0<=buffer<=120: raise ValueError('Arrival buffer must be 0–120 minutes')
    if not isinstance(modes,list) or not modes or any(m not in ('bus','rail','walk') for m in modes): raise ValueError('Choose valid modes')
    home=preferences(c)['home']
    if 'home' in body:
        if body.get('save_home') is not True: raise ValueError('Explicit consent is required to save Home')
        home=coordinates(body['home']) if body['home'] is not None else None
    c.execute('UPDATE transport_preferences SET arrival_buffer=?,modes=?,home_lat=?,home_lon=? WHERE id=1',(buffer,json.dumps(list(dict.fromkeys(modes))),*(home or [None,None])))
    return preferences(c)

def event(c, key):
    imported=re.fullmatch(r'calendar:(\d+):([a-f0-9]{20})',str(key))
    if imported:
        row=c.execute('SELECT id,event_uid,start_at,location,all_day FROM calendar_events WHERE id=?',(imported[1],)).fetchone()
        if not row or row[4] or transport_places.calendar_key(row)!=key:
            raise ValueError('Imported event no longer exists in this account. Reload Travel.')
        if not row[3].strip(): raise ValueError('This imported event has no destination.')
        when=datetime.fromisoformat(row[2])
        if when.tzinfo is None: when=when.replace(tzinfo=ZoneInfo('Europe/London'))
        return when.astimezone(timezone.utc),row[3]
    match=re.fullmatch(r'event:(\d+)',str(key))
    if not match: raise ValueError('Choose an Align event or imported calendar event')
    ident=match.group(1)
    row=c.execute('SELECT start_at,location,all_day FROM organiser_events WHERE id=?',(ident,)).fetchone()
    if not row or row[2]: raise ValueError('Choose an event with a start time')
    start,destination=row[:2]
    if not destination.strip(): raise ValueError('Save a destination on this item first')
    when=datetime.fromisoformat(start)
    if when.tzinfo is None: when=when.replace(tzinfo=ZoneInfo('Europe/London'))
    return when.astimezone(timezone.utc),destination

def cache_safe(result):
    saved=copy.deepcopy(result)
    # All provider free text is untrusted; strip origin/destination endpoint names
    # from stored routes. Geometry and precise coordinates never enter this model.
    for j in saved['journeys']:
        if j['legs']:
            j['legs'][0]['from']='Start'
            j['legs'][-1]['to']='Destination'
    return saved

def cached(c,key):
    event(c,key)  # A deleted / foreign item cannot reveal an old saved journey.
    row=c.execute('SELECT payload,updated_at,expires_at FROM transport_journey_cache WHERE event_key=?',(key,)).fetchone()
    if not row: return {'state':'no_cache','journeys':[]}
    result=json.loads(row[0]); result.update(cached=True,live=False,updated_at=row[1],expired=timestamp(row[2])<datetime.now(timezone.utc),message='Scheduled journey — live updates unavailable')
    for j in result['journeys']:
        j['live']=False
        for l in j['legs']: l['live']=False
    return result

def plan(c,body,provider=None):
    key=body.get('event_key')
    start,destination=event(c,key)
    prefs=preferences(c)
    target=start-timedelta(minutes=prefs['arrival_buffer'])
    if target<=datetime.now(timezone.utc): raise ValueError('Choose a future event')
    if body.get('location_consent') is not True: raise ValueError('Confirm sending these locations to the journey provider')
    def place(point, address):
        if point: return coordinates(point)
        if os.environ.get('ALIGN_JOURNEY_PROVIDER') != 'here': raise ValueError('Choose a matching place first')
        text=str(address or '').strip()
        if not 3<=len(text)<=240: raise ValueError('Enter a full address')
        from personal_planner import here_point
        found=here_point(os.environ.get('ALIGN_HERE_ROUTING_KEY',''),text)
        return coordinates([found['lat'],found['lng']])
    origin=place(body.get('origin') or (prefs['home'] if not body.get('origin_address') else None),body.get('origin_address'))
    dest=place(body.get('destination'),body.get('destination_address'))
    if provider is None:
        if os.environ.get('ALIGN_JOURNEY_PROVIDER') == 'here':
            from here_transit import HERETransitProvider
            provider = HERETransitProvider()
        else:
            provider = OTPProvider()
    try:
        candidates=provider.plan(origin,dest,target,prefs['modes'])
        # Arrive-by planners can return no result if all services arrive late.
        # A second bounded search retrieves late alternatives, still ranked
        # against the ORIGINAL target, never labelled on time.
        if not candidates:
            candidates=provider.plan(origin,dest,target+timedelta(hours=1),prefs['modes'])
    except ProviderUnavailable:
        result=cached(c,key)
        result['message']='Journey provider unavailable. '+result.get('message','No saved journey is available.')
        return result
    result=rank(candidates,target,prefs['modes'])
    now=datetime.now(timezone.utc)
    result.update(updated_at=now.isoformat(),cached=False,message=('No journey meets the arrival target.' if result['state']=='late' else 'No matching journeys found.' if result['state']=='no_journeys' else ''))
    if result['journeys']:
        c.execute('INSERT INTO transport_journey_cache VALUES(?,?,?,?) ON CONFLICT(event_key) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at,expires_at=excluded.expires_at',(key,json.dumps(cache_safe(result)),now.isoformat(),(now+timedelta(minutes=15)).isoformat()))
        c.execute('DELETE FROM transport_journey_cache WHERE event_key NOT IN (SELECT event_key FROM transport_journey_cache ORDER BY updated_at DESC LIMIT 100)')
    return result

def live(c,body):
    key=body['event_key']; result=cached(c,key)
    if not result['journeys']: return result
    candidates=result['journeys']; refreshed=False
    for journey in candidates:
        for name in ('bods','darwin'):
            try: updates=StatusHook(name).refresh(journey['legs'])
            except ProviderUnavailable: continue
            if not updates: continue
            for update in updates.get('legs',[]):
                for leg in journey['legs']:
                    # Exact service, stop pair and scheduled departure match.
                    if all(update.get(k)==leg.get(k) for k in ('service','from','to','start')):
                        for field in ('expected_start','expected_end','cancelled','platform'):
                            if field in update: leg[field]=update[field]
                        journey['disruption']=update.get('disruption','none')
                        refreshed=True; journey['live']=True; journey['updated_at']=datetime.now(timezone.utc).isoformat()
    if not refreshed: return result
    start,_=event(c,key); prefs=preferences(c)
    fresh=rank(candidates,start-timedelta(minutes=prefs['arrival_buffer']),prefs['modes'])
    fresh.update(updated_at=datetime.now(timezone.utc).isoformat(),cached=False)
    return fresh

def handle(handler,app,method):
    path=urlparse(handler.path).path
    if not path.startswith('/api/transport/'): return False
    try:
        # Bounded body consumption before rejection avoids unread-body resets.
        body=handler.read_json() if method=='POST' else {}
        if not isinstance(body,dict): raise ValueError('Expected an object')
        if app.BETA_MODE and not handler.require_beta_user(): return True
        if method=='POST':
            if app.BETA_MODE:
                if not handler.beta_same_origin(): return True
            elif handler.headers.get('Origin') not in (None,'http://'+handler.headers.get('Host',''),'https://'+handler.headers.get('Host','')):
                handler.send_json(403,{'error':'Use the current Align site'}); return True
        if path=='/api/transport/status':
            handler.send_json(200,{'enabled':enabled(),**routing_status(),'live_configured':{name:bool(os.environ.get('ALIGN_'+name+'_LIVE_URL') and os.environ.get('ALIGN_'+name+'_TOKEN')) for name in ('BODS','DARWIN')}}); return True
        if not enabled():
            handler.send_json(404,{'error':'Transport is disabled'}); return True
        with app.db_connection() as c:
            if path=='/api/transport/items' and method=='GET': result=transport_places.items(c)
            elif path=='/api/transport/places' and method=='POST': result=transport_places.lookup(body)
            elif path=='/api/transport/preferences': result=save_preferences(c,body) if method=='POST' else preferences(c)
            elif path=='/api/transport/nearby' and method=='POST': result={'stops':NaptanProvider().nearby(coordinates(body['origin']))}
            elif path=='/api/transport/journeys' and method=='POST': result=plan(c,body)
            elif path=='/api/transport/cached' and method=='POST': result=cached(c,body['event_key'])
            elif path=='/api/transport/live' and method=='POST': result=live(c,body)
            else:
                handler.send_json(404,{'error':'Not found'}); return True
        handler.send_json(200,result)
    except (ValueError,TypeError,KeyError,OverflowError):
        handler.send_json(400,{'error':'Check the event, coordinates, modes and location consent.'})
    except (OSError,RuntimeError):
        handler.send_json(503,{'error':'Transport unavailable; check server setup.'})
    return True
