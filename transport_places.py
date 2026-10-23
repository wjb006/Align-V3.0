"""Explicit place lookup; local stops need no external location disclosure."""
import json,re,hashlib,os
from pathlib import Path
from datetime import datetime,timezone,timedelta

def request_json(url):
    """Keep the Studio place-lookup seam patchable for privacy tests."""
    from personal_planner import fetch_json
    return fetch_json(url)

def lookup(body):
    q=str(body.get('query','')).strip()
    if not 2<=len(q)<=240: raise ValueError('Enter a stop name or full postcode')
    stops=json.loads(Path(__file__).with_name('merseyside_stops.json').read_text(encoding='utf-8'))
    matches=[s for s in stops if q.casefold() in s['name'].casefold()]
    if matches and not re.fullmatch(r'[A-Z]{1,2}\d[A-Z\d]?',re.sub(r'\s+','',q).upper()):
        return {'places':sorted(matches,key=lambda s:(s['name'].casefold()!=q.casefold(),s['name']))[:25]}
    if body.get('local_only') is True: return {'places':[]}
    postcode_query=re.sub(r'\s+','',q).upper()
    is_postcode_prefix=bool(re.fullmatch(r'[A-Z]{1,2}\d[A-Z\d]?',postcode_query) or re.fullmatch(r'[A-Z]{1,2}\d[A-Z\d]?\d[A-Z]{2}',postcode_query))
    if not is_postcode_prefix and body.get('consent') is True and os.environ.get('ALIGN_JOURNEY_PROVIDER') == 'here' and os.environ.get('ALIGN_HERE_ROUTING_KEY'):
        from personal_planner import here_fetch
        from urllib.parse import urlencode
        result=here_fetch('https://autosuggest.search.hereapi.com/v1/autosuggest?'+urlencode({'q':q,'in':'countryCode:GBR','limit':8,'lang':'en-GB','apiKey':os.environ.get('ALIGN_HERE_ROUTING_KEY','')}))
        places=[]
        for item in result.get('items',[]):
            position=item.get('position') or {}
            address=item.get('address') or {}
            name=address.get('label') or item.get('title') or ''
            if not name: continue
            place={'name':name}
            if position.get('lat') is not None and position.get('lng') is not None:
                place['point']=[position['lat'],position['lng']]
            places.append(place)
            if len(places)==8: break
        return {'places':places}
    if is_postcode_prefix:
        if body.get('consent') is not True: raise ValueError('Allow postcode lookup first')
        from urllib.parse import urlencode
        result=request_json('https://api.postcodes.io/postcodes/'+postcode_query+'/autocomplete?'+urlencode({'limit':8}))
        postcodes=result.get('result',[])
        if postcodes and isinstance(postcodes[0],str):
            from urllib.parse import quote
            postcodes=[request_json('https://api.postcodes.io/postcodes/'+quote(code,safe=''))['result'] for code in postcodes[:8]]
        return {'places':[{'name':item['postcode'],'point':[item['latitude'],item['longitude']]} for item in postcodes if isinstance(item,dict) and item.get('postcode') and item.get('latitude') is not None and item.get('longitude') is not None]}
    if body.get('consent') is True:
        from urllib.parse import urlencode
        result=request_json('https://photon.komoot.io/api?'+urlencode({'q':q,'limit':8,'lang':'en'}))
        places=[]
        for item in result.get('features',[]):
            properties=item.get('properties') or {}
            geometry=item.get('geometry') or {}
            coordinates=geometry.get('coordinates') or []
            country=str(properties.get('country') or '').casefold()
            country_code=str(properties.get('countrycode') or '').casefold()
            if country and country not in {'united kingdom','great britain'} and country_code!='gb': continue
            if len(coordinates)<2: continue
            street=' '.join(filter(None,[str(properties.get('housenumber') or '').strip(),str(properties.get('street') or '').strip()]))
            name=str(properties.get('name') or '').strip()
            if not street: street=name
            label=', '.join(dict.fromkeys(filter(None,[street,properties.get('postcode'),properties.get('city') or properties.get('town') or properties.get('village'),properties.get('state')])))
            if not label: continue
            places.append({'name':label,'point':[coordinates[1],coordinates[0]]})
            if len(places)==8: break
        return {'places':places}
    return {'places':[],'message':'No matching local stop. Allow live suggestions or search by postcode.'}

def calendar_key(row):
    return 'calendar:' + str(row[0]) + ':' + hashlib.sha256(str(row[1]).encode()).hexdigest()[:20]


def items(c):
    result=[]
    cutoff=(datetime.now(timezone.utc)-timedelta(days=1)).date().isoformat()
    for r in c.execute("SELECT id,title,start_at,location FROM organiser_events WHERE all_day=0 AND start_at>=? ORDER BY start_at LIMIT 300", (cutoff,)):
        result.append({'key':'event:'+str(r[0]),'title':r[1],'start':r[2],'destination':r[3]})
    for r in c.execute("SELECT id,event_uid,title,start_at,location FROM calendar_events WHERE all_day=0 AND start_at>=? AND TRIM(location)<>'' ORDER BY start_at LIMIT 300", (cutoff,)):
        result.append({'key':calendar_key(r),'title':r[2],'start':r[3],'destination':r[4]})
    now=datetime.now(timezone.utc)
    from zoneinfo import ZoneInfo
    def upcoming(item):
        try:
            start=datetime.fromisoformat(item['start'])
            if not start.tzinfo: start=start.replace(tzinfo=ZoneInfo('Europe/London'))
            return bool(item['destination'].strip()) and start>now
        except (ValueError, TypeError):
            return False
    return {'items':sorted((item for item in result if upcoming(item)),key=lambda r:r['start'])}
