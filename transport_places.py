"""Explicit place lookup; local stops need no external location disclosure."""
import json,re,hashlib,os
from pathlib import Path
from urllib.parse import quote
from datetime import datetime,timezone,timedelta
from transport_providers import request_json

def lookup(body):
    q=str(body.get('query','')).strip()
    if not 2<=len(q)<=240: raise ValueError('Enter a stop name or full postcode')
    stops=json.loads(Path(__file__).with_name('merseyside_stops.json').read_text(encoding='utf-8'))
    matches=[s for s in stops if q.casefold() in s['name'].casefold()]
    if matches: return {'places':sorted(matches,key=lambda s:(s['name'].casefold()!=q.casefold(),s['name']))[:25]}
    if body.get('local_only') is True: return {'places':[]}
    if body.get('consent') is True and os.environ.get('ALIGN_JOURNEY_PROVIDER') == 'here':
        from personal_planner import here_fetch
        from urllib.parse import urlencode
        result=here_fetch('https://geocode.search.hereapi.com/v1/geocode?'+urlencode({'q':q,'in':'countryCode:GBR','limit':5,'apiKey':os.environ.get('ALIGN_HERE_ROUTING_KEY','')}))
        return {'places':[{'name':item.get('title',q),'point':[item['position']['lat'],item['position']['lng']]} for item in result.get('items',[]) if item.get('position') and item.get('resultType') not in ('locality','administrativeArea') and float((item.get('scoring') or {}).get('queryScore') or 0)>=0.7]}
    codes=re.findall(r'\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b',q.upper())
    if not codes: return {'places':[],'message':'No matching local stop. Try a full postcode.'}
    if body.get('consent') is not True: raise ValueError('Allow postcode lookup first')
    data=request_json('https://api.postcodes.io/postcodes/'+quote(codes[-1]))
    r=data.get('result')
    if not r: return {'places':[]}
    return {'places':[{'name':r['postcode'],'point':[r['latitude'],r['longitude']]}]}

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
