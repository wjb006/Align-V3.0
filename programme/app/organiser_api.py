"""Organiser sections and events."""
from __future__ import annotations

import hashlib
import re
import sqlite3
from datetime import datetime, timedelta
from urllib.parse import urlparse

from colour_utils import colour as valid_colour


def rows_as_dicts(cursor: sqlite3.Cursor) -> list[dict]:
    return [dict(row) for row in cursor.fetchall()]


def organiser_sections(connection: sqlite3.Connection, include_inactive: bool = False) -> list[dict]:
    import app as align

    align.ensure_import_categories(connection)
    where = "" if include_inactive else " WHERE active=1"
    rows = rows_as_dicts(connection.execute(
        f"""SELECT s.*,l.calendar_url,l.calendar_name,l.import_enabled,l.export_enabled,
                    (SELECT COUNT(*) FROM organiser_events e WHERE e.section_id=s.id) AS align_event_count,
                    (SELECT COUNT(*) FROM calendar_sources cs JOIN calendar_events ce ON ce.source_id=cs.id
                       WHERE cs.section_id=s.id) AS imported_event_count
             FROM organiser_sections s
             LEFT JOIN calendar_links l ON l.target_kind='organiser_section' AND l.target_key=CAST(s.id AS TEXT){where}
             ORDER BY sort_order,name"""
    ))
    for row in rows:
        row["calendar_id"] = hashlib.sha256(row["calendar_url"].encode()).hexdigest() if row.get("calendar_url") else ""
        row.pop("calendar_url", None)
    return rows


def organiser_section(connection: sqlite3.Connection, section_id: int) -> dict:
    row = connection.execute("""SELECT s.*,l.calendar_url,l.calendar_name,l.import_enabled,l.export_enabled
        FROM organiser_sections s LEFT JOIN calendar_links l
          ON l.target_kind='organiser_section' AND l.target_key=CAST(s.id AS TEXT)
        WHERE s.id=? AND s.active=1""", (section_id,)).fetchone()
    if not row:
        raise ValueError("Section not found.")
    section = dict(row)
    section["calendar_id"] = hashlib.sha256(section["calendar_url"].encode()).hexdigest() if section.get("calendar_url") else ""
    section.pop("calendar_url", None)
    now = (datetime.now() - timedelta(days=31)).isoformat(timespec="minutes")
    align_events = rows_as_dicts(connection.execute(
        """SELECT id,section_id,title,start_at,end_at,all_day,location,notes,'align' AS source_kind
             FROM organiser_events WHERE section_id=? AND end_at>=? ORDER BY start_at LIMIT 500""",
        (section_id, now),
    ))
    imported = rows_as_dicts(connection.execute(
        """SELECT ce.id,cs.section_id,ce.title,ce.start_at,ce.end_at,ce.all_day,ce.location,'' AS notes,
                    'icloud' AS source_kind, cs.name AS source_name
             FROM calendar_events ce JOIN calendar_sources cs ON cs.id=ce.source_id
             WHERE cs.section_id=? AND ce.end_at>=? ORDER BY ce.start_at LIMIT 1000""",
        (section_id, now),
    ))
    from post_event_travel import decorate
    section["events"] = decorate(connection, sorted(align_events + imported, key=lambda item: (item["start_at"], item.get("title", ""))))
    return section


def section_values(payload: dict, calendar_resolver=None, connection: sqlite3.Connection | None = None) -> tuple:
    from admin_api import validate_parent_branch

    name = str(payload.get("name", "")).strip()[:80]
    if not name:
        raise ValueError("Give this section a name.")
    description = str(payload.get("description", "")).strip()[:180]
    icon = str(payload.get("icon", "•")).strip()[:4] or "•"
    colour = valid_colour(str(payload.get("colour", "#365CE6")))
    calendar_url = ""
    calendar_name = ""
    calendar_id = str(payload.get("calendar_id", "")).strip()
    if calendar_id:
        if calendar_resolver is None:
            raise ValueError("Reconnect iCloud before linking this section to a calendar.")
        calendar_url, calendar_name = calendar_resolver(calendar_id)
    parent_id = int(payload.get("parent_branch_id") or 0) or None
    if parent_id and connection is not None:
        validate_parent_branch(connection, parent_id)
    return (name, description, icon, colour, 1 if payload.get("active", True) else 0,
            int(payload.get("sort_order", 100)), parent_id, calendar_url, calendar_name,
            1 if payload.get("import_enabled", True) else 0,
            1 if payload.get("export_enabled", True) else 0)


def save_calendar_link(connection, section_id: int, values: tuple) -> None:
    _, _, _, _, _, _, _, calendar_url, calendar_name, import_enabled, export_enabled = values
    key = str(section_id)
    if not calendar_url:
        connection.execute("DELETE FROM calendar_links WHERE target_kind='organiser_section' AND target_key=?", (key,))
        return
    connection.execute("""INSERT INTO calendar_links
        (target_kind,target_key,calendar_url,calendar_name,import_enabled,export_enabled)
        VALUES('organiser_section',?,?,?,?,?)
        ON CONFLICT(target_kind,target_key) DO UPDATE SET calendar_url=excluded.calendar_url,
        calendar_name=excluded.calendar_name,import_enabled=excluded.import_enabled,
        export_enabled=excluded.export_enabled""",
        (key, calendar_url, calendar_name, import_enabled, export_enabled))


def organiser_event_values(payload: dict) -> tuple:
    title = str(payload.get("title", "")).strip()[:160]
    if not title:
        raise ValueError("Give this event a title.")
    all_day = bool(payload.get("all_day", False))
    if all_day:
        import app as align
        start_date = align.valid_iso_date(str(payload.get("date") or payload.get("start_date") or ""))
        end_date = align.valid_iso_date(str(payload.get("end_date") or start_date))
        start = datetime.fromisoformat(start_date + "T00:00")
        end = datetime.fromisoformat(end_date + "T00:00") + timedelta(days=1)
    else:
        start_raw = str(payload.get("start_at", "")).strip()
        end_raw = str(payload.get("end_at", "")).strip()
        try:
            start = datetime.fromisoformat(start_raw)
            end = datetime.fromisoformat(end_raw)
        except ValueError as error:
            raise ValueError("Choose a valid event date and time.") from error
        if end <= start:
            raise ValueError("Event end time must be after its start time.")
    return (title, start.isoformat(timespec="minutes"), end.isoformat(timespec="minutes"),
            1 if all_day else 0, str(payload.get("location", "")).strip()[:240],
            (__import__("travel_refresh").clean(str(payload.get("notes", ""))) if all_day else str(payload.get("notes", "")).strip())[:4000])


def event_section_for_calendar(connection: sqlite3.Connection, calendar_id: str, fallback_section: int | None = None) -> int:
    """Find or create the quick-add Section for an explicitly chosen iCloud calendar."""
    if not calendar_id:
        if fallback_section and connection.execute(
            'SELECT 1 FROM organiser_sections WHERE id=? AND active=1', (fallback_section,)
        ).fetchone():
            return fallback_section
        raise ValueError('Choose a calendar or create a new calendar before saving this event.')
    row = connection.execute(
        "SELECT calendar_url,calendar_name FROM calendar_links WHERE target_kind='icloud_calendar' AND target_key=?",
        (calendar_id,),
    ).fetchone()
    if not row:
        raise ValueError('That calendar is no longer selected. Refresh your calendar list and try again.')
    existing = connection.execute(
        "SELECT s.id FROM organiser_sections s JOIN calendar_links l "
        "ON l.target_kind='organiser_section' AND l.target_key=CAST(s.id AS TEXT) "
        "WHERE s.active=1 AND l.calendar_url=? ORDER BY s.id LIMIT 1", (row['calendar_url'],)
    ).fetchone()
    if existing:
        return existing['id']
    name = (row['calendar_name'] or 'Calendar')[:80]
    section = connection.execute(
        "INSERT INTO organiser_sections(name,description,icon,colour,calendar_name,import_enabled,export_enabled) "
        "VALUES(?,?,'▦','#365CE6',?,1,1)",
        (name, 'Events saved to this iCloud calendar', name),
    )
    connection.execute("""INSERT INTO calendar_links
        (target_kind,target_key,calendar_url,calendar_name,import_enabled,export_enabled)
        VALUES('organiser_section',?,?,?,1,1)
        ON CONFLICT(target_kind,target_key) DO UPDATE SET calendar_url=excluded.calendar_url,
        calendar_name=excluded.calendar_name,import_enabled=1,export_enabled=1""",
        (str(section.lastrowid), row['calendar_url'], name))
    return section.lastrowid


def _wake(handler, app, row) -> None:
    manager = handler.request_icloud_manager(row) if app.BETA_MODE else app.ICLOUD_MANAGER
    if manager and manager.enabled:
        manager.wake.set()


def handle(handler, app, method, connection, payload=None, row=None) -> bool:
    import post_event_travel

    path = urlparse(handler.path).path
    if method == "GET" and path == "/api/sections":
        handler.send_json(200, organiser_sections(connection))
        return True
    if method == "GET" and re.fullmatch(r"/api/sections/\d+", path):
        handler.send_json(200, organiser_section(connection, int(path.rsplit("/", 1)[1])))
        return True
    if method == "POST" and path == "/api/sections":
        manager = handler.request_icloud_manager(row) if app.BETA_MODE else app.ICLOUD_MANAGER

        def resolver(calendar_id):
            if manager is None:
                raise ValueError("Connect iCloud from PC Admin before linking a calendar.")
            return manager.resolve_calendar(calendar_id)

        values = section_values(payload, resolver if payload.get("calendar_id") else None, connection)
        cursor = connection.execute(
            """INSERT INTO organiser_sections
               (name,description,icon,colour,active,sort_order,parent_branch_id)
               VALUES(?,?,?,?,?,?,?)""", values[:7])
        save_calendar_link(connection, cursor.lastrowid, values)
        handler.send_json(201, {"id": cursor.lastrowid})
        if manager and manager.enabled:
            manager.wake.set()
        return True
    event_match = re.fullmatch(r"/api/sections/(\d+)/events", path)
    if method == "POST" and event_match:
        requested_calendar = str(payload.get('calendar_id', '')).strip()
        section_id = event_section_for_calendar(connection, requested_calendar, int(event_match.group(1))) if requested_calendar else int(event_match.group(1))
        if not connection.execute("SELECT 1 FROM organiser_sections WHERE id=? AND active=1", (section_id,)).fetchone():
            raise ValueError("Section not found.")
        values = organiser_event_values(payload)
        request_id = str(payload.get("request_id", "")).strip()[:120] or None
        if request_id:
            existing = connection.execute("SELECT id FROM organiser_events WHERE request_id=?", (request_id,)).fetchone()
            if existing:
                handler.send_json(200, {"id": existing["id"], "duplicate": True})
                return True
        cursor = connection.execute(
            "INSERT INTO organiser_events(section_id,title,start_at,end_at,all_day,location,notes,request_id) VALUES(?,?,?,?,?,?,?,?)",
            (section_id, *values, request_id),
        )
        if "show_post_travel" in payload:
            post_event_travel.handle(connection, dict(kind="event", id=cursor.lastrowid, enabled=payload["show_post_travel"], mode=payload.get("post_travel_mode", "transit")))
        handler.send_json(201, {"id": cursor.lastrowid, "section_id": section_id})
        _wake(handler, app, row)
        return True
    section_match = re.fullmatch(r"/api/sections/(\d+)", path)
    if method == "PUT" and section_match:
        section_id = int(section_match.group(1))
        current = connection.execute("""SELECT s.*,l.calendar_url,l.calendar_name
            FROM organiser_sections s LEFT JOIN calendar_links l
              ON l.target_kind='organiser_section' AND l.target_key=CAST(s.id AS TEXT)
            WHERE s.id=?""", (section_id,)).fetchone()
        if not current:
            raise ValueError("Section not found.")
        requested_id = str(payload.get("calendar_id", "")).strip()
        current_id = hashlib.sha256(current["calendar_url"].encode()).hexdigest() if current["calendar_url"] else ""

        def resolver(calendar_id):
            if calendar_id == current_id and current["calendar_url"]:
                return current["calendar_url"], current["calendar_name"]
            manager = handler.request_icloud_manager(row) if app.BETA_MODE else app.ICLOUD_MANAGER
            if manager is None:
                raise ValueError("Reconnect iCloud before changing this calendar link.")
            return manager.resolve_calendar(calendar_id)

        values = section_values(payload, resolver if requested_id else None, connection)
        connection.execute(
            """UPDATE organiser_sections SET name=?,description=?,icon=?,colour=?,active=?,sort_order=?,parent_branch_id=?
               WHERE id=?""", (*values[:7], section_id))
        save_calendar_link(connection, section_id, values)
        handler.send_json(200, {"id": section_id})
        _wake(handler, app, row)
        return True
    event_put = re.fullmatch(r"/api/organiser-events/(\d+)", path)
    if method == "PUT" and event_put:
        event_id = int(event_put.group(1))
        if not connection.execute("SELECT 1 FROM organiser_events WHERE id=?", (event_id,)).fetchone():
            raise ValueError("Event not found.")
        requested_calendar = str(payload.get('calendar_id', '')).strip()
        current_section = connection.execute('SELECT section_id FROM organiser_events WHERE id=?', (event_id,)).fetchone()['section_id']
        section_id = event_section_for_calendar(connection, requested_calendar, current_section) if requested_calendar else current_section
        connection.execute(
            "UPDATE organiser_events SET title=?,start_at=?,end_at=?,all_day=?,location=?,notes=? WHERE id=?",
            (*organiser_event_values(payload), event_id),
        )
        connection.execute('UPDATE organiser_events SET section_id=? WHERE id=?', (section_id, event_id))
        if "show_post_travel" in payload:
            post_event_travel.handle(connection, dict(kind="event", id=event_id, enabled=payload["show_post_travel"], mode=payload.get("post_travel_mode", "transit")))
        handler.send_json(200, {"id": event_id, "section_id": section_id})
        _wake(handler, app, row)
        return True
    if method == "DELETE" and re.fullmatch(r"/api/sections/\d+", path):
        section_id = int(path.rsplit("/", 1)[1])
        connection.execute("DELETE FROM calendar_links WHERE target_kind='organiser_section' AND target_key=?", (str(section_id),))
        connection.execute("DELETE FROM organiser_sections WHERE id=?", (section_id,))
        handler.send_json(200, {"ok": True})
        _wake(handler, app, row)
        return True
    if method == "DELETE" and re.fullmatch(r"/api/organiser-events/\d+", path):
        event_id = int(path.rsplit("/", 1)[1])
        connection.execute("DELETE FROM organiser_events WHERE id=?", (event_id,))
        handler.send_json(200, {"ok": True})
        _wake(handler, app, row)
        return True
    return False
