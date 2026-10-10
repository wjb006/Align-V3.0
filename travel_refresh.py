"""Invalidate derived journey notes when their saved inputs change."""
import hashlib
import json
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

KEY = 'derived_travel_state_v1'
PENDING = '[Align travel pending]'
BLOCKS = re.compile(r'\n?\[Align travel(?: steps)?\][\s\S]*?(?:\[/Align travel(?: steps)?\]|$)', re.I)

def clean(notes):
    return BLOCKS.sub('', notes or '').replace(PENDING, '').strip()

def load(c):
    row=c.execute('SELECT setting_value FROM settings WHERE setting_key=?',(KEY,)).fetchone()
    return json.loads(row[0]) if row else {}

def save(c, data):
    c.execute('INSERT INTO settings(setting_key,setting_value) VALUES(?,?) ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value',(KEY,json.dumps(data)))

def records(c):
    now=datetime.now(ZoneInfo('Europe/London')).isoformat(timespec='minutes')[:16]
    rows=[]
    for r in c.execute("SELECT s.id,s.work_date,s.start_time,s.notes,COALESCE(NULLIF(l.address,''),s.location_name) FROM shifts s LEFT JOIN locations l ON l.id=s.location_id WHERE s.work_date>=?",(now[:10],)):
        rows.append(dict(key='shift:'+str(r[0]),table='shifts',id=r[0],arrival=r[1]+'T'+r[2],notes=r[3] or '',destination=r[4] or ''))
    for r in c.execute('SELECT id,start_at,notes,location FROM organiser_events WHERE all_day=0 AND start_at>=?',(now,)):
        rows.append(dict(key='event:'+str(r[0]),table='organiser_events',id=r[0],arrival=r[1][:16],notes=r[2] or '',destination=r[3] or ''))
    return [r for r in rows if r['arrival']>now]

def mode(notes, fallback):
    if 'Driving estimate:' in notes:return 'drive'
    try:
        match=re.search(r'\[Align travel steps\]([\s\S]*?)\[/Align travel steps\]',notes)
        modes={s.get('mode') for s in json.loads(match[1])} if match else set()
        bus='bus' in modes; rail=bool(modes & {'train','rail'})
        if bus or rail:return 'transit' if bus and rail else 'bus' if bus else 'train'
    except (ValueError,TypeError):pass
    return fallback

def synchronize(c):
    from personal_planner import preferences
    prefs=preferences(c)
    home=c.execute("SELECT setting_value FROM settings WHERE setting_key='user_address'").fetchone()
    home=home[0] if home else ''
    data=load(c); current={}; changed=False
    for r in records(c):
        old=data.get(r['key'],{})
        has_travel='[Align travel]' in r['notes'] or PENDING in r['notes']
        inputs=[home,r['destination'],r['arrival'],{k:prefs.get(k) for k in ('default_travel','departure_buffer','arrival_buffer','weather_adjustments','weather_rain_threshold','weather_rain_buffer','weather_storm_buffer','traffic_buffer_cap')}]
        signature=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()
        entry=dict(old)
        if old.get('signature')!=signature:
            entry={'signature':signature,'pending':has_travel,'mode':mode(r['notes'],old.get('mode',prefs['default_travel'])),'retry':0}
            # Phone origins cannot be safely replaced with home during a refresh.
            if 'current location' in r['notes'].lower():entry['phone']=True
            if has_travel:c.execute(f"UPDATE {r['table']} SET notes=? WHERE id=?",((clean(r['notes'])+'\n'+PENDING).strip(),r['id']))
            changed=True
        if not has_travel:entry['pending']=False
        current[r['key']]=entry
    changed=changed or set(data)!=set(current)
    if changed:
        # Cached route coordinates/results refer to the old inputs.
        from sqlite_support import postgres_enabled
        exists=c.execute("SELECT table_name FROM information_schema.tables WHERE table_schema=current_schema() AND table_name='transport_journey_cache'" if postgres_enabled() else "SELECT name FROM sqlite_master WHERE type='table' AND name='transport_journey_cache'").fetchone()
        if exists:c.execute('DELETE FROM transport_journey_cache')
    save(c,current)
    return sum(bool(v.get('pending')) for v in current.values())

def refresh_one(c):
    from personal_planner import journey
    synchronize(c); data=load(c)
    for r in records(c):
        entry=data.get(r['key'],{})
        if not entry.get('pending') or entry.get('retry',0)>time.time() or entry.get('phone'):continue
        try:
            result=journey(c,{'destination':r['destination'],'arrival':r['arrival'],'mode':entry['mode']})
            plan=(result.get('journeys') or [result])[0]
            if not plan.get('notes'):raise ValueError('No journey found')
            notes=clean(r['notes'])+'\n[Align travel]\n'+plan['notes']+'\n[/Align travel]'
            if plan.get('steps'):notes+='\n[Align travel steps]\n'+json.dumps(plan['steps'])+'\n[/Align travel steps]'
            synchronize(c)
            latest=load(c)
            if latest.get(r['key'],{}).get('signature')!=entry['signature']:
                return {'remaining':sum(bool(v.get('pending')) for v in latest.values()),'ready':1}
            updated=c.execute(f"UPDATE {r['table']} SET notes=? WHERE id=? AND notes=?",(notes.strip(),r['id'],r['notes']))
            entry['pending']=updated.rowcount!=1
            data=latest
            data[r['key']]=entry
        except (ValueError,OSError,RuntimeError):
            entry['retry']=time.time()+300
        break
    save(c,data)
    return {'remaining':sum(bool(v.get('pending')) for v in data.values()),'ready':sum(bool(v.get('pending')) and not v.get('phone') and v.get('retry',0)<=time.time() for v in data.values())}

def location_changed(c, old, new):
    """Keep future events using an exact saved address in step with that address."""
    if not old or old==new:return
    now=datetime.now(ZoneInfo('Europe/London')).isoformat(timespec='minutes')[:16]
    c.execute('UPDATE organiser_events SET location=? WHERE location=? AND start_at>=?',(new,old,now))
