"""Planner schedule, shift, leave, alert, and calendar routes.

Restored from the Align beta planner with V3-compatible route handling.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from urllib.parse import parse_qs


def _rows(connection, sql, args=()):
    return [dict(row) for row in connection.execute(sql, args).fetchall()]


def _iso_date(value):
    return date.fromisoformat(str(value or "")).isoformat()


def _time(value):
    parsed = datetime.strptime(str(value or ""), "%H:%M")
    return parsed.strftime("%H:%M")


def _hours(start, end, break_minutes=0):
    a = datetime.strptime(start, "%H:%M")
    b = datetime.strptime(end, "%H:%M")
    if b <= a:
        b += timedelta(days=1)
    result = (b-a).total_seconds()/3600 - int(break_minutes or 0)/60
    if result <= 0:
        raise ValueError("A shift must be longer than its break.")
    return round(result, 2)


def _bounds(day, start, end):
    a = datetime.fromisoformat(f"{day}T{start}")
    b = datetime.fromisoformat(f"{day}T{end}")
    if b <= a:
        b += timedelta(days=1)
    return a, b


def _overlap(day, start, end, other):
    a,b = _bounds(day,start,end)
    c,d = _bounds(other["work_date"],other["start_time"],other["end_time"])
    return a < d and c < b


def _check_shift(connection, day, start, end, exclude_id=None):
    leave = connection.execute("SELECT 1 FROM annual_leave WHERE leave_date=?", (day,)).fetchone()
    if leave:
        raise ValueError(f"{day} is booked as annual leave.")
    check_day = date.fromisoformat(day)
    rows = connection.execute(
        "SELECT id,work_date,start_time,end_time,location_name FROM shifts WHERE work_date BETWEEN ? AND ?",
        ((check_day-timedelta(days=1)).isoformat(),(check_day+timedelta(days=1)).isoformat())
    ).fetchall()
    for row in rows:
        other = dict(row)
        if exclude_id is not None and int(other["id"]) == int(exclude_id):
            continue
        if _overlap(day,start,end,other):
            raise ValueError(f"{day}: {start}–{end} overlaps {other['location_name']}.")
    a,b = _bounds(day,start,end)
    imported = connection.execute(
        "SELECT title,start_at,end_at FROM calendar_events WHERE start_at < ? AND end_at > ?",
        (b.isoformat(),a.isoformat())
    ).fetchall()
    for event in imported:
        raise ValueError(f"{day}: this clashes with {event['title'] or 'an imported calendar event'}.")
    organiser = connection.execute(
        "SELECT title,start_at,end_at FROM organiser_events WHERE start_at < ? AND end_at > ?",
        (b.isoformat(),a.isoformat())
    ).fetchall()
    for event in organiser:
        raise ValueError(f"{day}: this clashes with {event['title'] or 'an Align event'}.")


def _templates(connection):
    return _rows(connection, """SELECT t.id,t.location_id,t.shift_type_id,t.label,t.sub_shift_type,
        t.start_time,t.end_time,t.break_minutes,t.applicable_days,t.active,
        l.name AS location_name,l.address AS location_address,l.colour AS location_colour,
        s.name AS shift_type_name,s.colour AS shift_type_colour
        FROM shift_templates t JOIN locations l ON l.id=t.location_id
        JOIN shift_types s ON s.id=t.shift_type_id WHERE t.active=1 AND l.active=1 AND s.active=1
        ORDER BY l.name,t.start_time,t.label""")

def _shift_values(connection, payload, fallback_date=None):
    template_id = payload.get("template_id")
    template = None
    if template_id not in (None, ""):
        template = connection.execute(
            """SELECT t.*,l.name AS location_name,l.colour AS location_colour,
               s.name AS shift_type_name,s.colour AS shift_type_colour
               FROM shift_templates t JOIN locations l ON l.id=t.location_id
               JOIN shift_types s ON s.id=t.shift_type_id WHERE t.id=? AND t.active=1""",
            (int(template_id),)
        ).fetchone()
        if not template:
            raise ValueError("Choose a valid saved shift pattern.")
    day = _iso_date(payload.get("work_date") or fallback_date or "")
    start = _time(payload.get("start_time") or (template["start_time"] if template else ""))
    end = _time(payload.get("end_time") or (template["end_time"] if template else ""))
    break_minutes = int(payload.get("break_minutes", template["break_minutes"] if template else 0))
    if not 0 <= break_minutes <= 720:
        raise ValueError("Break must be between 0 and 720 minutes.")
    hours = _hours(start,end,break_minutes)
    location_id = int(payload.get("location_id") or template["location_id"]) if (payload.get("location_id") or template) else None
    type_id = int(payload.get("shift_type_id") or template["shift_type_id"]) if (payload.get("shift_type_id") or template) else None
    location = connection.execute("SELECT name,colour FROM locations WHERE id=? AND active=1",(location_id,)).fetchone() if location_id else None
    shift_type = connection.execute("SELECT name,colour FROM shift_types WHERE id=? AND active=1",(type_id,)).fetchone() if type_id else None
    if not location or not shift_type:
        raise ValueError("Choose a work location and shift type, or select a saved shift pattern.")
    return (day, int(template_id) if template_id else None, location_id, type_id,
            location["name"], shift_type["name"], location["colour"] or shift_type["colour"],
            start,end,break_minutes,hours,str(payload.get("notes","")).strip()[:1000])


def _week(connection, raw_date):
    chosen = date.fromisoformat(_iso_date(raw_date))
    start = chosen - timedelta(days=chosen.weekday())
    end = start + timedelta(days=6)
    shifts = _rows(connection, """SELECT * FROM shifts WHERE work_date BETWEEN ? AND ?
        ORDER BY work_date,start_time,id""",(start.isoformat(),end.isoformat()))
    leave = _rows(connection,"SELECT * FROM annual_leave WHERE leave_date BETWEEN ? AND ? ORDER BY leave_date",(start.isoformat(),end.isoformat()))
    events = _rows(connection,"""SELECT e.*,s.name AS section_name FROM organiser_events e
        JOIN organiser_sections s ON s.id=e.section_id
        WHERE e.start_at < ? AND e.end_at >= ? ORDER BY e.start_at""",
        ((end+timedelta(days=1)).isoformat(),start.isoformat()))
    return {"start":start.isoformat(),"end":end.isoformat(),"shifts":shifts,"annual_leave":leave,"events":events,
            "locations":_rows(connection,"SELECT * FROM locations WHERE active=1 ORDER BY name"),
            "shift_types":_rows(connection,"SELECT * FROM shift_types WHERE active=1 ORDER BY name"),
            "templates":_templates(connection)}


def _month(connection, raw_month):
    month = str(raw_month or date.today().strftime("%Y-%m"))
    start = date.fromisoformat(month+"-01")
    end = date(start.year + (start.month==12), start.month%12+1, 1)-timedelta(days=1)
    data = _week(connection,start.isoformat())
    shifts = _rows(connection,"SELECT * FROM shifts WHERE work_date BETWEEN ? AND ? ORDER BY work_date,start_time",(start.isoformat(),end.isoformat()))
    leave = _rows(connection,"SELECT * FROM annual_leave WHERE leave_date BETWEEN ? AND ? ORDER BY leave_date",(start.isoformat(),end.isoformat()))
    return {"month":month,"start":start.isoformat(),"end":end.isoformat(),"shifts":shifts,"annual_leave":leave,
            "locations":data["locations"],"shift_types":data["shift_types"],"templates":data["templates"]}


def handle_get(handler, app, connection, parsed, row) -> bool:
    self = handler
    path = parsed.path
    query = parse_qs(parsed.query)
    if path == "/api/bootstrap":
        self.send_json(200, {"build_version": app.BUILD_VERSION,
            "personal": app.personal_planner.bootstrap(connection),
            "builder": app.owner_builder.bootstrap(app.DATABASE, connection),
            "settings": app.get_settings(connection), "dashboard": app.dashboard(connection),
            "calendar": app.calendar_data(connection), "sections": app.organiser_sections(connection),
            "navigation": app.navigation_data(connection),
            "icloud_public": app.public_icloud_data(self.request_icloud_manager(row) if app.BETA_MODE else None),
            "icloud_event_calendars": app.icloud_event_calendars(connection),
            "beta": ({"email":row["email"],"is_owner":bool(row["is_owner"])} if row else None)})
        return True
    if path == "/api/week":
        self.send_json(200,_week(connection,query.get("start",[date.today().isoformat()])[0])); return True
    if path == "/api/month":
        self.send_json(200,_month(connection,query.get("month",[date.today().strftime("%Y-%m")])[0])); return True
    if path == "/api/shifts":
        start = query.get("start",[None])[0]; end = query.get("end",[None])[0]
        sql = "SELECT * FROM shifts"; args=[]
        if start and end: sql += " WHERE work_date BETWEEN ? AND ?"; args=[_iso_date(start),_iso_date(end)]
        sql += " ORDER BY work_date,start_time,id"
        self.send_json(200,{"shifts":_rows(connection,sql,args)}); return True
    if path == "/api/annual-leave":
        start=query.get("start",[None])[0]; end=query.get("end",[None])[0]
        sql="SELECT * FROM annual_leave"; args=[]
        if start and end: sql+=" WHERE leave_date BETWEEN ? AND ?"; args=[_iso_date(start),_iso_date(end)]
        sql+=" ORDER BY leave_date"
        self.send_json(200,{"annual_leave":_rows(connection,sql,args)}); return True
    if path in ("/api/locations","/api/user-locations"):
        self.send_json(200,{"locations":_rows(connection,"SELECT * FROM locations WHERE active=1 ORDER BY name")}); return True
    if path == "/api/shift-types":
        self.send_json(200,{"shift_types":_rows(connection,"SELECT * FROM shift_types WHERE active=1 ORDER BY name")}); return True
    if path == "/api/templates":
        self.send_json(200,{"templates":_templates(connection)}); return True
    if path == "/api/alert-rules":
        self.send_json(200,{"alert_rules":_rows(connection,"SELECT * FROM alert_rules ORDER BY id")}); return True
    if path == "/api/dashboard":
        self.send_json(200,app.dashboard(connection)); return True
    if path == "/api/address-search":
        results=app.find_addresses(query.get("q",[""])[0]); self.send_json(200,{"provider":results[0].get("provider","Address search") if results else "Address search","results":results}); return True
    if path == "/api/calendars":
        self.send_json(200,app.calendar_data(connection)); return True
    if path in {"/api/calendars/align.ics","/api/calendars/live.ics"}:
        self.send_calendar(connection,download=path.endswith("/align.ics")); return True
    return False


def handle_post(handler, app, connection, path, payload, row) -> bool:
    self=handler
    if path == "/api/shifts":
        items=payload.get("shifts") if isinstance(payload.get("shifts"),list) else [payload]
        if not items or len(items)>100: raise ValueError("Choose between 1 and 100 shifts.")
        request_id=str(payload.get("request_id") or "")
        if request_id:
            cached=connection.execute("SELECT result_json FROM shift_batches WHERE request_id=?",(request_id,)).fetchone()
            if cached:
                self.send_json(200,{"shifts":json.loads(cached["result_json"])}); return True
        saved=[]
        for item in items:
            values=_shift_values(connection,item)
            _check_shift(connection,values[0],values[7],values[8])
            cur=connection.execute("""INSERT INTO shifts(work_date,template_id,location_id,shift_type_id,location_name,shift_type_name,colour,start_time,end_time,break_minutes,hours,notes)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",values)
            saved.append({"id":cur.lastrowid,"work_date":values[0],"location_name":values[4],"shift_type_name":values[5],"start_time":values[7],"end_time":values[8],"hours":values[10]})
        if request_id:
            connection.execute("INSERT INTO shift_batches(request_id,payload_hash,result_json) VALUES(?,?,?)",(request_id,"",json.dumps(saved)))
        connection.commit()
        self.send_json(201,{"shifts":saved})
        return True
    if path == "/api/annual-leave":
        start=date.fromisoformat(_iso_date(payload.get("start_date") or payload.get("leave_date")))
        end=date.fromisoformat(_iso_date(payload.get("end_date") or start.isoformat()))
        if end<start: raise ValueError("End date must be on or after the start date.")
        notes=str(payload.get("notes","")).strip()[:500]; days=[]; current=start
        while current<=end:
            iso=current.isoformat()
            if not connection.execute("SELECT 1 FROM shifts WHERE work_date=?",(iso,)).fetchone() and not connection.execute("SELECT 1 FROM annual_leave WHERE leave_date=?",(iso,)).fetchone():
                connection.execute("INSERT INTO annual_leave(leave_date,notes) VALUES(?,?)",(iso,notes)); days.append(iso)
            current+=timedelta(days=1)
        connection.commit(); self.send_json(201,{"start_date":start.isoformat(),"end_date":end.isoformat(),"days":len(days)}); return True
    if path in ("/api/locations","/api/user-locations"):
        name=str(payload.get("name","")).strip()
        if not name: raise ValueError("Location name is required.")
        cur=connection.execute("INSERT INTO locations(name,address,colour) VALUES(?,?,?)",(name,str(payload.get("address","")).strip(),str(payload.get("colour","#365CE6"))))
        connection.commit(); self.send_json(201,{"id":cur.lastrowid}); return True
    if path == "/api/shift-types":
        name=str(payload.get("name","")).strip()
        if not name: raise ValueError("Shift type name is required.")
        cur=connection.execute("INSERT INTO shift_types(name,colour) VALUES(?,?)",(name,str(payload.get("colour","#3B82F6"))))
        connection.commit(); self.send_json(201,{"id":cur.lastrowid}); return True
    if path == "/api/templates":
        location_id=int(payload.get("location_id") or 0); type_id=int(payload.get("shift_type_id") or 0)
        label=str(payload.get("label","")).strip()
        if not label: raise ValueError("Shift pattern name is required.")
        start=_time(payload.get("start_time")); end=_time(payload.get("end_time")); break_minutes=int(payload.get("break_minutes",0)); _hours(start,end,break_minutes)
        cur=connection.execute("INSERT INTO shift_templates(location_id,shift_type_id,label,sub_shift_type,start_time,end_time,break_minutes,applicable_days) VALUES(?,?,?,?,?,?,?,?)",(location_id,type_id,label,str(payload.get("sub_shift_type",""))[:80],start,end,break_minutes,json.dumps(payload.get("applicable_days",[]))))
        connection.commit(); self.send_json(201,{"id":cur.lastrowid}); return True
    if path == "/api/alert-rules":
        title=str(payload.get("title","Shift reminder")).strip()[:120]; minutes=int(payload.get("minutes_before",15))
        if not 0<=minutes<=10080: raise ValueError("Reminder must be between 0 and 7 days.")
        cur=connection.execute("INSERT INTO alert_rules(title,minutes_before,active) VALUES(?,?,?)",(title,minutes,1))
        connection.commit(); self.send_json(201,{"id":cur.lastrowid}); return True
    if path == "/api/calendars/import":
        source_id,count=app.import_ics_calendar(connection,str(payload.get("name","")),str(payload.get("ics","")))
        self.send_json(201,{"id":source_id,"events":count}); return True
    return False


def handle_put(handler, app, connection, path, payload, row) -> bool:
    self=handler
    if path.startswith("/api/shifts/"):
        item_id=int(path.rsplit("/",1)[1])
        existing=connection.execute("SELECT * FROM shifts WHERE id=?",(item_id,)).fetchone()
        if not existing: raise ValueError("Shift not found.")
        merged=dict(existing); merged.update(payload)
        values=_shift_values(connection,merged,existing["work_date"])
        _check_shift(connection,values[0],values[7],values[8],item_id)
        connection.execute("""UPDATE shifts SET work_date=?,template_id=?,location_id=?,shift_type_id=?,location_name=?,shift_type_name=?,colour=?,start_time=?,end_time=?,break_minutes=?,hours=?,notes=? WHERE id=?""",(*values,item_id))
        connection.commit(); self.send_json(200,{"id":item_id}); return True
    if path.startswith("/api/templates/"):
        item_id=int(path.rsplit("/",1)[1]); existing=connection.execute("SELECT * FROM shift_templates WHERE id=?",(item_id,)).fetchone()
        if not existing: raise ValueError("Shift pattern not found.")
        merged=dict(existing); merged.update(payload)
        start=_time(merged["start_time"]); end=_time(merged["end_time"]); break_minutes=int(merged.get("break_minutes",0)); _hours(start,end,break_minutes)
        connection.execute("UPDATE shift_templates SET location_id=?,shift_type_id=?,label=?,sub_shift_type=?,start_time=?,end_time=?,break_minutes=?,applicable_days=? WHERE id=?",(int(merged["location_id"]),int(merged["shift_type_id"]),str(merged["label"]).strip(),str(merged.get("sub_shift_type","")),start,end,break_minutes,json.dumps(merged.get("applicable_days",[])) if isinstance(merged.get("applicable_days",[]),list) else merged.get("applicable_days","[]"),item_id))
        connection.commit(); self.send_json(200,{"id":item_id}); return True
    if path.startswith("/api/locations/"):
        item_id=int(path.rsplit("/",1)[1]); name=str(payload.get("name","")).strip()
        if not name: raise ValueError("Location name is required.")
        connection.execute("UPDATE locations SET name=?,address=?,colour=? WHERE id=?",(name,str(payload.get("address","")).strip(),str(payload.get("colour","#365CE6")),item_id)); connection.commit(); self.send_json(200,{"id":item_id}); return True
    return False


def handle_delete(handler, app, connection, path, row) -> bool:
    self=handler
    if path.startswith("/api/shifts/"):
        connection.execute("DELETE FROM shifts WHERE id=?",(int(path.rsplit("/",1)[1]),)); connection.commit(); self.send_json(200,{"ok":True}); return True
    if path.startswith("/api/annual-leave/"):
        connection.execute("DELETE FROM annual_leave WHERE id=?",(int(path.rsplit("/",1)[1]),)); connection.commit(); self.send_json(200,{"ok":True}); return True
    if path.startswith("/api/alert-rules/"):
        connection.execute("DELETE FROM alert_rules WHERE id=?",(int(path.rsplit("/",1)[1]),)); connection.commit(); self.send_json(200,{"ok":True}); return True
    if path.startswith("/api/templates/"):
        connection.execute("UPDATE shift_templates SET active=0 WHERE id=?",(int(path.rsplit("/",1)[1]),)); connection.commit(); self.send_json(200,{"ok":True}); return True
    if path.startswith("/api/locations/"):
        connection.execute("UPDATE locations SET active=0 WHERE id=?",(int(path.rsplit("/",1)[1]),)); connection.commit(); self.send_json(200,{"ok":True}); return True
    if path.startswith("/api/calendars/"):
        connection.execute("DELETE FROM calendar_sources WHERE id=?",(int(path.rsplit("/",1)[1]),)); self.send_json(200,{"ok":True}); return True
    return False
