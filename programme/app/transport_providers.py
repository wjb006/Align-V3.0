"""Provider adapters. No endpoint or credential is accepted from a browser."""
import csv
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlparse

class ProviderUnavailable(Exception):
    pass

def request_json(url, body=None, headers=None):
    parsed=urlparse(url)
    if parsed.scheme!='https' and not (parsed.scheme=='http' and parsed.hostname in ('localhost','127.0.0.1','::1')):
        raise ProviderUnavailable('Provider needs HTTPS (or a loopback server)')
    try:
        request=Request(url,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json',**(headers or {})})
        with urlopen(request,timeout=8) as response:
            data=response.read(4_000_001)
        if len(data)>4_000_000: raise ValueError('Response too large')
        return json.loads(data)
    except Exception:
        # URLs, coordinates, credentials and upstream bodies never enter errors.
        raise ProviderUnavailable('Transport provider unavailable') from None

class OTPProvider:
    """OTP 2 GTFS GraphQL plan API; configure endpoint and feed graph separately.

    The legacy plan field remains supported in OTP 2 deployments; pin an OTP
    release exposing that schema. BODS bus and licensed rail schedules populate
    its graph, OSM supplies pedestrian paths, and realtime updaters supply delays.
    """
    query='''query($from:InputCoordinates!,$to:InputCoordinates!,$date:String!,$time:String!,$modes:[TransportMode!]) {
      plan(from:$from,to:$to,date:$date,time:$time,arriveBy:true,numItineraries:12,searchWindow:7200,transportModes:$modes) {
        itineraries { legs { mode startTime endTime realTime departureDelay arrivalDelay
          from { name stop { platformCode } } to { name } route { shortName longName } } }
      }
    }'''
    legacy_query='''query($from:InputCoordinates!,$to:InputCoordinates!,$date:String!,$time:String!,$modes:[TransportMode!]) {
      plan(from:$from,to:$to,date:$date,time:$time,arriveBy:true,numItineraries:12,searchWindow:7200,transportModes:$modes) {
        itineraries { legs { mode startTime endTime realTime departureDelay arrivalDelay
          from { name } to { name } route { shortName longName } } }
      }
    }'''
    def plan(self, origin, destination, target, modes, depart_after=False):
        endpoint=os.environ.get('ALIGN_OTP_URL','http://127.0.0.1:8080/otp/gtfs/v1')
        if not endpoint: raise ProviderUnavailable('Journey provider setup required')
        from zoneinfo import ZoneInfo
        local=target.astimezone(ZoneInfo('Europe/London'))
        mapping={'walk':'WALK','bus':'BUS','rail':'RAIL'}
        variables={'from':{'lat':origin[0],'lon':origin[1]},'to':{'lat':destination[0],'lon':destination[1]},'date':local.strftime('%Y-%m-%d'),'time':local.strftime('%H:%M:%S'),'modes':[{'mode':mapping[m]} for m in modes]}
        query = self.query.replace('arriveBy:true','arriveBy:false') if depart_after else self.query
        result=request_json(endpoint,{'query':query,'variables':variables})
        if result.get('errors'):
            # Older pinned OTP schemas may not expose Place.stop.platformCode.
            # Fall back without platform data instead of breaking journey planning.
            query = self.legacy_query.replace('arriveBy:true','arriveBy:false') if depart_after else self.legacy_query
            result=request_json(endpoint,{'query':query,'variables':variables})
        if result.get('errors'): raise ProviderUnavailable('Journey provider schema/configuration error')
        journeys=[]
        for itinerary in (result.get('data',{}).get('plan') or {}).get('itineraries',[]):
            legs=[]
            for leg in itinerary['legs']:
                mode={'WALK':'walk','BUS':'bus','RAIL':'rail','SUBWAY':'rail','TRAM':'rail'}.get(leg['mode'],'unsupported')
                start=datetime.fromtimestamp(leg['startTime']/1000,timezone.utc)
                end=datetime.fromtimestamp(leg['endTime']/1000,timezone.utc)
                route=leg.get('route') or {}
                from_place=leg.get('from') or {}
                platform=((from_place.get('stop') or {}).get('platformCode') or '') if mode=='rail' else ''
                legs.append({'mode':mode,'start':start.isoformat(),'end':end.isoformat(),'from':from_place.get('name') or '','to':(leg.get('to') or {}).get('name') or '','service':route.get('shortName') or route.get('longName') or '', 'service_number':route.get('shortName') or '', 'platform':platform, 'live':bool(leg.get('realTime'))})
            journeys.append({'legs':legs,'live':any(l['live'] for l in legs),'updated_at':datetime.now(timezone.utc).isoformat(),'provider':'OpenTripPlanner','disruption':'none'})
        return journeys

def distance(a,b):
    lat1,lon1,lat2,lon2=map(math.radians,(*a,*b))
    return 6371000*2*math.asin(min(1,math.sqrt(math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2)))

class NaptanProvider:
    def nearby(self, origin):
        path=os.environ.get('ALIGN_NAPTAN_CSV','')
        if not path: return []
        stops=[]
        with Path(path).open(encoding='utf-8-sig',newline='') as f:
            for row in csv.DictReader(f):
                try:
                    point=float(row['Latitude']),float(row['Longitude'])
                    mode='rail' if row.get('StopType') in ('RLY','RPL','MET','PLT') else 'bus'
                    metres=distance(origin,point)
                    if metres <= (2500 if mode=='rail' else 800): stops.append({'id':row['ATCOCode'],'name':row.get('CommonName',''),'mode':mode,'metres':round(metres),'lat':point[0],'lon':point[1]})
                except (KeyError,ValueError): continue
        stops.sort(key=lambda s:(s['metres'],s['id']))
        return [s for mode,limit in [('bus',5),('rail',3)] for s in [s for s in stops if s['mode']==mode][:limit]]

class StatusHook:
    """Optional server-side BODS/Darwin bridge with the normalized leg contract.

    A bridge converts SIRI / Darwin IDs to the graph's service/stop identities.
    Without this mapping we never infer delays from vehicle positions.
    """
    def __init__(self,name): self.name=name
    def refresh(self, legs):
        prefix='ALIGN_'+self.name.upper()
        endpoint=os.environ.get(prefix+'_LIVE_URL','')
        token=os.environ.get(prefix+'_TOKEN','')
        if not endpoint or not token: return None
        # Transit identifiers only, no home address or current coordinates.
        services=[{k:l.get(k) for k in ('service','from','to','start','end')} for l in legs if l['mode']==('bus' if self.name=='bods' else 'rail')]
        return request_json(endpoint,{'services':services},{'Authorization':'Bearer '+token})
