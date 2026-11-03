"""Deterministic ranking from JOURNEY_RANKING_RULES.md. All times are UTC-aware."""
from datetime import datetime, timezone
import hashlib
import json

def timestamp(value):
    result = datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if result.tzinfo is None:
        raise ValueError('Transport times must include a UTC offset')
    return result.astimezone(timezone.utc)

def minutes(a,b):
    return (a-b).total_seconds()/60

def rank(journeys, target, modes, now=None):
    target = timestamp(target) if isinstance(target,str) else target
    now = now or datetime.now(timezone.utc)
    valid = {}
    for raw in journeys:
        try:
            j = dict(raw)
            legs = j['legs']
            if not legs or j.get('unusable') or j.get('disruption') == 'cancelled': continue
            times = [(timestamp(l.get('expected_start') or l['start']),timestamp(l.get('expected_end') or l['end'])) for l in legs]
            if any(l['mode'] not in modes or l.get('cancelled') or b<a for l,(a,b) in zip(legs,times)): continue
            if any(times[i][0] < times[i-1][1] for i in range(1,len(times))): continue
            if times[0][0] < now: continue
            transit = [i for i,l in enumerate(legs) if l['mode'] != 'walk']
            changes = max(0,len(transit)-1)
            margins=[]
            for a,b in zip(transit,transit[1:]):
                walking_between=sum(minutes(times[k][1],times[k][0]) for k in range(a+1,b))
                margins.append(minutes(times[b][0],times[a][1])-walking_between)
            margin=min(margins) if margins else None
            risk=0 if not changes else (4 if margin is None else 20 if margin<3 else 10 if margin<5 else 4 if margin<8 else 0)
            duration=minutes(times[-1][1],times[0][0])
            walk=sum(minutes(b,a) for l,(a,b) in zip(legs,times) if l['mode']=='walk')
            waiting=sum(minutes(times[i][0],times[i-1][1]) for i in range(1,len(times)))
            arrival_margin=minutes(target,times[-1][1])
            arrival_penalty=(100-5*arrival_margin if arrival_margin<0 else 4*(5-arrival_margin) if arrival_margin<5 else 0 if arrival_margin<=20 else .1*(arrival_margin-20) if arrival_margin<=45 else 2.5+.25*(arrival_margin-45))
            age=max(0,minutes(now,timestamp(j.get('updated_at') or now.isoformat())))
            live=bool(j.get('live'))
            freshness=(0 if age<=5 else 2 if age<=10 else 5 if age<=20 else 12) if live else 2
            disruption=j.get('disruption','none')
            bucket={'major':1,'severe':2}.get(disruption,0)
            score=duration+12*changes+.6*walk+.25*waiting+risk+arrival_penalty+{'minor':4,'major':15,'severe':40}.get(disruption,0)+freshness
            signature=json.dumps([(l['mode'],l.get('service',''),l.get('from',''),l.get('to',''),l['start'],l['end']) for l in legs])
            jid=hashlib.sha256(signature.encode()).hexdigest()[:24]
            j.update(id=jid,duration=round(duration,2),walking=round(walk,2),waiting=waiting,changes=changes,transfer_risk=risk,score=score,reliability=bucket,arrival_margin=arrival_margin,departure=times[0][0].isoformat(),arrival=times[-1][1].isoformat(),freshness=freshness,badges=[])
            if jid not in valid or (freshness,not live)<(valid[jid]['freshness'],not valid[jid].get('live')): valid[jid]=j
        except (ValueError,KeyError,TypeError,OverflowError):
            continue
    pool=list(valid.values())
    on_time=[j for j in pool if j['arrival_margin']>=0]
    pool=on_time or pool
    if not pool: return {'state':'no_journeys','journeys':[], 'target':target.isoformat()}
    def key(j, mode):
        later=-timestamp(j['departure']).timestamp()
        tie=(j['freshness'],j['changes'],j['walking'],later,j['id'])
        if not on_time: return (timestamp(j['arrival']),j['reliability'],j['score'],*tie)
        fields={'Recommended':(j['score'],j['changes'],j['walking'],j['duration'],later),
                'Fastest':(j['duration'],j['changes'],j['walking'],later),
                'Fewest changes':(j['changes'],j['transfer_risk'],j['duration'],j['walking'],later),
                'Least walking':(j['walking'],j['changes'],j['duration'],later)}
        return (j['reliability'],*fields[mode],*tie)
    ordered=sorted(pool,key=lambda j:key(j,'Recommended'))
    for mode in ('Recommended','Fastest','Fewest changes','Least walking'):
        winner=min(pool,key=lambda j:key(j,mode))
        winner['badges'].append(mode if on_time else 'Earliest arrival')
        winner['badges']=list(dict.fromkeys(winner['badges']))
    # Preserve winners even when the provider returns many candidates.
    winners=[j for j in ordered if j['badges']]
    selected=winners+[j for j in ordered if not j['badges']][:max(0,8-len(winners))]
    return {'state':'on_time' if on_time else 'late','journeys':selected,'target':target.isoformat(),'earliest_arrival':min(j['arrival'] for j in pool)}
