"""Planner schedule, shift, leave, alert, and calendar routes."""
from __future__ import annotations

from datetime import date, timedelta
from urllib.parse import parse_qs


def handle_get(handler, app, connection, parsed, row) -> bool:
    self = handler
    BETA_MODE = app.BETA_MODE
    BUILD_VERSION = app.BUILD_VERSION
    DATABASE = app.DATABASE
    alert_rules = app.alert_rules
    calendar_data = app.calendar_data
    dashboard = app.dashboard
    find_addresses = app.find_addresses
    get_settings = app.get_settings
    master_data = app.master_data
    month_data = app.month_data
    next_week_options = app.next_week_options
    organiser_sections = app.organiser_sections
    owner_builder = app.owner_builder
    personal_planner = app.personal_planner
    public_icloud_data = app.public_icloud_data
    shift_query = app.shift_query
    week_data = app.week_data
    if parsed.path == "/api/bootstrap":
        self.send_json(200, {"build_version": BUILD_VERSION, "personal": personal_planner.bootstrap(connection), "builder": owner_builder.bootstrap(DATABASE, connection), "settings": get_settings(connection), "master": master_data(connection), "dashboard": dashboard(connection), "calendar": calendar_data(connection), "sections": organiser_sections(connection), "icloud_public": public_icloud_data(self.request_icloud_manager(row) if BETA_MODE else None), "beta": ({"email":row["email"],"is_owner":bool(row["is_owner"])} if row else None), "week_options": next_week_options(connection)})
        return True
    if parsed.path == '/api/week':
        self.send_json(200, week_data(connection, parse_qs(parsed.query).get('start', [date.today().isoformat()])[0]))
        return True
    if parsed.path == '/api/month':
        self.send_json(200, month_data(connection, parse_qs(parsed.query).get('month', [date.today().strftime('%Y-%m')])[0]))
        return True
    if parsed.path == "/api/dashboard":
        self.send_json(200, dashboard(connection))
        return True
    if parsed.path == "/api/address-search":
        query = parse_qs(parsed.query).get("q", [""])[0]
        self.send_json(200, {"provider":"UK address search","results": find_addresses(query)})
        return True
    if parsed.path == "/api/calendars":
        self.send_json(200, calendar_data(connection))
        return True
    if parsed.path in {"/api/calendars/align.ics", "/api/calendars/live.ics"}:
        self.send_calendar(connection, download=parsed.path.endswith("/align.ics"))
        return True
    if parsed.path == "/api/alert-rules":
        self.send_json(200, alert_rules(connection))
        return True
    if parsed.path == "/api/shifts":
        query = parse_qs(parsed.query)
        self.send_json(200, shift_query(connection, query.get("start", [None])[0], query.get("end", [None])[0]))
        return True
    return False


def handle_post(handler, app, connection, path, payload, row) -> bool:
    self = handler
    BETA_MODE = app.BETA_MODE
    ICLOUD_MANAGER = app.ICLOUD_MANAGER
    alert_rule_values = app.alert_rule_values
    create_shifts = app.create_shifts
    import_ics_calendar = app.import_ics_calendar
    leave_balance = app.leave_balance
    rebuild_shift_alerts = app.rebuild_shift_alerts
    save_location_categories = app.save_location_categories
    valid_colour = app.valid_colour
    valid_iso_date = app.valid_iso_date
    if path == "/api/shifts":
        saved = create_shifts(connection, payload)
        connection.commit()
        self.send_json(201, {"shifts": saved})
        manager = self.request_icloud_manager(row) if BETA_MODE else ICLOUD_MANAGER
        if manager and manager.enabled: manager.wake.set()
        return True
    if path == "/api/alert-rules":
        values = alert_rule_values(payload)
        cursor = connection.execute("INSERT INTO alert_rules(title,minutes_before,active) VALUES(?,?,?)", values)
        rebuild_shift_alerts(connection)
        self.send_json(201, {"id": cursor.lastrowid})
        return True
    if path == "/api/leave":
        start = date.fromisoformat(valid_iso_date(str(payload.get("start_date") or payload.get("leave_date") or "")))
        end = date.fromisoformat(valid_iso_date(str(payload.get("end_date") or start)))
        if end < start: raise ValueError('End date must be on or after the start date.')
        notes = str(payload.get("notes", "")).strip()[:500]
        booked=[]; day=start
        while day <= end:
            if not connection.execute("SELECT 1 FROM annual_leave WHERE leave_date=?", (day.isoformat(),)).fetchone():
                connection.execute("INSERT INTO annual_leave(leave_date, notes) VALUES (?, ?)", (day.isoformat(), notes)); booked.append(day.isoformat())
            day += timedelta(days=1)
        self.send_json(201, {"start_date": start.isoformat(), "end_date": end.isoformat(), "days": len(booked), "leave_balance": leave_balance(connection)})
        return True
    if path == "/api/calendars/import":
        source_id, count = import_ics_calendar(
            connection, str(payload.get("name", "")), str(payload.get("ics", ""))
        )
        self.send_json(201, {"id": source_id, "events": count})
        return True
    if path == "/api/user-locations":
        name = str(payload.get("name", "")).strip()
        if not name:
            raise ValueError("Location name is required.")
        cursor = connection.execute(
            "INSERT INTO locations(name, address) VALUES (?, ?)",
            (name, str(payload.get("address", "")).strip()),
        )
        save_location_categories(connection, cursor.lastrowid, payload.get("shift_type_ids"))
        if 'colour' in payload:
            connection.execute('UPDATE locations SET colour=? WHERE id=?', (valid_colour(payload['colour']), cursor.lastrowid))
        self.send_json(201, {"id": cursor.lastrowid})
        return True
    return False


def handle_put(handler, app, connection, path, payload, row) -> bool:
    self = handler
    BETA_MODE = app.BETA_MODE
    ICLOUD_MANAGER = app.ICLOUD_MANAGER
    alert_rule_values = app.alert_rule_values
    create_shift_alert = app.create_shift_alert
    dated_shifts_overlap = app.dated_shifts_overlap
    hours_between = app.hours_between
    apply_cover_note = app.apply_cover_note
    imported_conflict = app.imported_conflict
    organiser_conflict = app.organiser_conflict
    rebuild_shift_alerts = app.rebuild_shift_alerts
    save_location_categories = app.save_location_categories
    shift_notes = app.shift_notes
    valid_colour = app.valid_colour
    valid_iso_date = app.valid_iso_date
    valid_time = app.valid_time
    if path.startswith("/api/alert-rules/"):
        item_id = int(path.rsplit("/", 1)[1])
        if not connection.execute("SELECT 1 FROM alert_rules WHERE id=?", (item_id,)).fetchone():
            raise ValueError("Alert rule not found.")
        connection.execute("UPDATE alert_rules SET title=?,minutes_before=?,active=? WHERE id=?", (*alert_rule_values(payload), item_id))
        rebuild_shift_alerts(connection)
        connection.commit()
        self.send_json(200, {"id": item_id})
        return True
    if path.startswith("/api/user-locations/"):
        item_id = int(path.rsplit("/", 1)[1])
        name = str(payload.get("name", "")).strip()
        if not name:
            raise ValueError("Location name is required.")
        from travel_refresh import location_changed
        previous=connection.execute('SELECT address FROM locations WHERE id=?',(item_id,)).fetchone()
        if previous: location_changed(connection, previous[0], str(payload.get('address','')).strip())
        connection.execute(
            "UPDATE locations SET name=?, address=? WHERE id=? AND active=1",
            (name, str(payload.get("address", "")).strip(), item_id),
        )
        save_location_categories(connection, item_id, payload.get("shift_type_ids"))
        if 'colour' in payload:
            connection.execute('UPDATE locations SET colour=? WHERE id=?', (valid_colour(payload['colour']), item_id))
        connection.commit()
        self.send_json(200, {"id": item_id})
        return True

    if path.startswith("/api/shifts/"):
        item_id = int(path.rsplit("/", 1)[1])
        start, end = valid_time(payload["start_time"]), valid_time(payload["end_time"])
        break_minutes = max(0, int(payload.get("break_minutes", 0)))
        if hours_between(start, end, break_minutes) <= 0:
            raise ValueError("A shift must be longer than its break.")
        shift = connection.execute("SELECT * FROM shifts WHERE id=?", (item_id,)).fetchone()
        if not shift:
            raise ValueError("Shift not found.")
        work_date = valid_iso_date(str(payload.get("work_date") or shift["work_date"]))
        if connection.execute("SELECT 1 FROM annual_leave WHERE leave_date=?", (work_date,)).fetchone():
            raise ValueError(f"{work_date} is booked as annual leave.")
        day = date.fromisoformat(work_date)
        for other in connection.execute(
            "SELECT work_date,start_time,end_time,location_name FROM shifts WHERE work_date BETWEEN ? AND ? AND id<>?",
            ((day-timedelta(days=1)).isoformat(), (day+timedelta(days=1)).isoformat(), item_id)
        ):
            if dated_shifts_overlap({'work_date': work_date, 'start_time': start, 'end_time': end}, other):
                raise ValueError(f"{work_date}: {start}–{end} overlaps {other['location_name']}.")
            if work_date == other['work_date'] and (start < '12:00') == (other['start_time'] < '12:00'):
                raise ValueError(f'{work_date}: a shift is already selected for this half of the day. Choose AM + PM.')
        calendar_title = imported_conflict(connection, work_date, start, end)
        if calendar_title:
            raise ValueError(f"{work_date}: this clashes with {calendar_title} in an imported calendar.")
        appointment = organiser_conflict(connection, work_date, start, end)
        if appointment:
            raise ValueError(f"{work_date}: this clashes with {appointment}.")
        notes = shift_notes(payload.get("notes", ""))
        if "cover" in payload:
            notes = apply_cover_note(notes, payload.get("cover"), payload.get("cover_name"))
        connection.execute(
            """UPDATE shifts SET work_date=?,start_time=?,end_time=?,break_minutes=?,hours=?,notes=?
               WHERE id=?""",
            (work_date, start, end, break_minutes, hours_between(start, end, break_minutes),
             notes, item_id),
        )
        connection.execute("DELETE FROM alerts WHERE shift_id=?", (item_id,))
        create_shift_alert(connection, item_id, work_date, start)
        connection.commit()
        self.send_json(200, {"id": item_id})
        manager = self.request_icloud_manager(row) if BETA_MODE else ICLOUD_MANAGER
        if manager and manager.enabled: manager.wake.set()
        return True
    return False


def handle_delete(handler, app, connection, path, row) -> bool:
    self = handler
    BETA_MODE = app.BETA_MODE
    ICLOUD_MANAGER = app.ICLOUD_MANAGER
    rebuild_shift_alerts = app.rebuild_shift_alerts
    if path.startswith("/api/alert-rules/"):
        connection.execute("DELETE FROM alert_rules WHERE id=?", (int(path.rsplit("/", 1)[1]),))
        rebuild_shift_alerts(connection)
        self.send_json(200, {"ok": True})
        return True
    if path.startswith("/api/shifts/"):
        connection.execute("DELETE FROM shifts WHERE id=?", (int(path.rsplit("/", 1)[1]),))
        self.send_json(200, {"ok": True})
        manager = self.request_icloud_manager(row) if BETA_MODE else ICLOUD_MANAGER
        if manager and manager.enabled: manager.wake.set()
        return True
    if path.startswith("/api/leave/"):
        connection.execute("DELETE FROM annual_leave WHERE id=?", (int(path.rsplit("/", 1)[1]),))
        self.send_json(200, {"ok": True})
        return True
    if path.startswith("/api/calendars/"):
        source_id = int(path.rsplit("/", 1)[1])
        connection.execute("DELETE FROM calendar_sources WHERE id=?", (source_id,))
        self.send_json(200, {"ok": True})
        return True
    return False
