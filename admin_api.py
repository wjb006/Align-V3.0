"""Local admin session and master-data routes."""
from __future__ import annotations

import json
import re
import secrets
import sqlite3
from datetime import date
from http import HTTPStatus
from urllib.parse import urlparse

from work_setup import colour as valid_colour

BRANCH_TYPES = {"profile", "work", "locations", "alerts", "calendar", "colours", "note"}
PARENT_DESTINATIONS = {"add", "calendar", "settings", "note", "submenu"}


def branch_values(payload: dict, existing_key: str | None = None) -> tuple:
    branch_type = str(payload.get("branch_type", "note"))
    if branch_type not in BRANCH_TYPES:
        raise ValueError("That menu branch type is not supported.")
    title = str(payload.get("title", "")).strip()[:80]
    if not title:
        raise ValueError("Menu branch title is required.")
    key = existing_key or "custom-" + secrets.token_hex(5)
    return (
        key, title, str(payload.get("description", "")).strip()[:200],
        str(payload.get("icon", "○")).strip()[:4] or "○", branch_type,
        str(payload.get("content", "")).strip()[:2000],
        1 if payload.get("active", True) else 0, int(payload.get("sort_order", 100)),
    )


def validate_parent_branch(connection: sqlite3.Connection, parent_id: int | None, item_id: int | None = None) -> int | None:
    if not parent_id:
        return None
    parent_id = int(parent_id)
    row = connection.execute("SELECT id,parent_id,destination FROM parent_menu_branches WHERE id=?", (parent_id,)).fetchone()
    if not row or row["destination"] != "submenu":
        raise ValueError("Menu items can only be moved inside a Submenu/folder.")
    if item_id and parent_id == item_id:
        raise ValueError("A menu item cannot contain itself.")
    seen = {item_id} if item_id else set()
    current = row
    while current:
        if current["id"] in seen:
            raise ValueError("That move would create a menu loop.")
        seen.add(current["id"])
        current = connection.execute("SELECT id,parent_id,destination FROM parent_menu_branches WHERE id=?", (current["parent_id"],)).fetchone() if current["parent_id"] else None
    return parent_id


def parent_branch_values(payload: dict, existing_key: str | None = None) -> tuple:
    destination = str(payload.get("destination", "note"))
    if destination not in PARENT_DESTINATIONS:
        raise ValueError("That parent menu destination is not supported.")
    title = str(payload.get("title", "")).strip()[:80]
    if not title:
        raise ValueError("Parent menu title is required.")
    parent_id = int(payload.get("parent_id") or 0) or None
    return (existing_key or "parent-" + secrets.token_hex(5), title,
        str(payload.get("description", "")).strip()[:200], str(payload.get("icon", "○")).strip()[:4] or "○", destination,
        str(payload.get("content", "")).strip()[:2000], 1 if payload.get("active", True) else 0, int(payload.get("sort_order", 100)),
        parent_id, valid_colour(str(payload.get("colour", "#365CE6"))), 1 if payload.get("locked", False) else 0, 1 if payload.get("optional", True) else 0)


def shift_pattern_values(connection: sqlite3.Connection, payload: dict, exclude_id: int | None = None) -> tuple:
    """Validate a reusable pattern and preserve the Location → Type → Sub-type model."""
    import app as align

    location_id = int(payload.get("location_id", 0))
    shift_type_id = int(payload.get("shift_type_id", 0))
    shift_type = connection.execute("SELECT name FROM shift_types WHERE id=?", (shift_type_id,)).fetchone()
    location = connection.execute("SELECT id FROM locations WHERE id=?", (location_id,)).fetchone()
    if not location or not shift_type:
        raise ValueError("Choose a valid location and shift type.")
    sub_shift_type = str(payload.get("sub_shift_type", payload.get("label", ""))).strip()[:60]
    if not sub_shift_type:
        raise ValueError("Sub-shift type is required (for example AM or PM).")
    start, end = align.valid_time(str(payload.get("start_time", ""))), align.valid_time(str(payload.get("end_time", "")))
    break_minutes = max(0, int(payload.get("break_minutes", 0)))
    if align.hours_between(start, end, break_minutes) <= 0:
        raise ValueError("A shift must be longer than its break.")
    applicable_days = align.normalise_applicable_days(payload.get("applicable_days"))
    duplicate = connection.execute(
        """SELECT id FROM shift_templates
           WHERE location_id=? AND shift_type_id=? AND sub_shift_type=?
             AND start_time=? AND end_time=? AND break_minutes=?
             AND (? IS NULL OR id <> ?)""",
        (location_id, shift_type_id, sub_shift_type, start, end, break_minutes, exclude_id, exclude_id),
    ).fetchone()
    if duplicate:
        raise ValueError("That location, shift type and sub-shift pattern already exists.")
    connection.execute(
        "INSERT OR IGNORE INTO location_shift_types(location_id,shift_type_id) VALUES (?,?)",
        (location_id, shift_type_id),
    )
    # label is retained for compatibility with earlier SQLite databases.  The
    # user-facing UI uses sub_shift_type so AM/PM remains a separate choice.
    label = f"{shift_type['name']} {sub_shift_type} {start}–{end}"
    return (
        location_id, shift_type_id, label, sub_shift_type, start, end, break_minutes,
        json.dumps(applicable_days), 1 if payload.get("active", True) else 0,
    )


def normalise_shift_type_ids(value: object) -> list[int]:
    if value is None:
        return []
    if not isinstance(value, list):
        value = [value]
    ids = []
    for item in value:
        try:
            item_id = int(item)
        except (TypeError, ValueError):
            continue
        if item_id > 0 and item_id not in ids:
            ids.append(item_id)
    return ids


def save_location_categories(connection: sqlite3.Connection, location_id: int, value: object) -> None:
    selected = set(normalise_shift_type_ids(value))
    valid = {
        row[0] for row in connection.execute(
            f"SELECT id FROM shift_types WHERE id IN ({','.join('?' for _ in selected)})", tuple(selected)
        )
    } if selected else set()
    if selected != valid:
        raise ValueError("One or more selected shift categories are no longer available.")
    # Keep categories used by saved patterns; hide or edit the pattern itself
    # rather than creating a location whose configuration contradicts it.
    selected.update(
        row[0] for row in connection.execute(
            "SELECT DISTINCT shift_type_id FROM shift_templates WHERE location_id=?", (location_id,)
        )
    )
    connection.execute("DELETE FROM location_shift_types WHERE location_id=?", (location_id,))
    connection.executemany(
        "INSERT INTO location_shift_types(location_id,shift_type_id) VALUES (?,?)",
        [(location_id, shift_type_id) for shift_type_id in selected],
    )


def _require(handler) -> bool:
    return handler.require_admin()


def handle(handler, app, method, connection=None, payload=None) -> bool:
    path = urlparse(handler.path).path

    # Schedule-planner APIs are retired in Align V3.0. Return an explicit 404
    # before touching legacy tables, including writes from stale clients.
    retired_schedule_paths = (
        path == "/api/locations"
        or re.fullmatch(r"/api/locations/\\d+", path)
        or path == "/api/shift-types"
        or re.fullmatch(r"/api/shift-types/\\d+", path)
        or path == "/api/templates"
        or re.fullmatch(r"/api/templates/\\d+(?:/apply)?", path)
    )
    if retired_schedule_paths:
        handler.send_json(HTTPStatus.NOT_FOUND, {"error": "This schedule-planning endpoint is no longer available."})
        return True

    if method == "GET" and path == "/api/admin/status":
        handler.send_json(200, {"password_required": bool(app.ADMIN_PASSWORD) if not app.BETA_MODE else False, "authenticated": handler.is_admin(), "beta": app.BETA_MODE})
        return True
    if method == "GET" and path == "/api/master":
        if not _require(handler):
            return True
        handler.send_json(200, app.master_data(connection, include_inactive=True))
        return True
    if method == "POST" and path == "/api/admin/login":
        if app.ADMIN_PASSWORD and not secrets.compare_digest(str(payload.get("password", "")), app.ADMIN_PASSWORD):
            handler.send_json(HTTPStatus.UNAUTHORIZED, {"error": "That admin password is not correct."})
            return True
        token = secrets.token_urlsafe(32)
        app.ADMIN_SESSIONS.add(token)
        handler.send_json(200, {"token": token, "password_required": bool(app.ADMIN_PASSWORD)})
        return True
    if connection is None:
        return False
    if method == "POST" and path == "/api/locations":
        if not _require(handler):
            return True
        name = str(payload.get("name", "")).strip()
        if not name:
            raise ValueError("Location name is required.")
        cursor = connection.execute("INSERT INTO locations(name, address) VALUES (?, ?)", (name, str(payload.get("address", "")).strip()))
        save_location_categories(connection, cursor.lastrowid, payload.get("shift_type_ids"))
        if "colour" in payload:
            connection.execute("UPDATE locations SET colour=? WHERE id=?", (valid_colour(payload["colour"]), cursor.lastrowid))
        handler.send_json(201, {"id": cursor.lastrowid})
        return True
    if method == "POST" and path == "/api/menu-branches":
        if not _require(handler):
            return True
        values = branch_values(payload)
        cursor = connection.execute(
            """INSERT INTO menu_branches
               (branch_key,title,description,icon,branch_type,content,active,sort_order)
               VALUES (?,?,?,?,?,?,?,?)""",
            values,
        )
        handler.send_json(201, {"id": cursor.lastrowid})
        return True
    if method == "POST" and path == "/api/parent-menu-branches":
        if not _require(handler):
            return True
        values = parent_branch_values(payload)
        validate_parent_branch(connection, values[8])
        cursor = connection.execute(
            """INSERT INTO parent_menu_branches
               (branch_key,title,description,icon,destination,content,active,sort_order,parent_id,colour,locked,optional)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", values)
        handler.send_json(201, {"id": cursor.lastrowid})
        return True
    if method == "POST" and path == "/api/shift-types":
        if not _require(handler):
            return True
        name = str(payload.get("name", "")).strip()
        if not name:
            raise ValueError("Shift type name is required.")
        cursor = connection.execute("INSERT INTO shift_types(name, colour) VALUES (?, ?)", (name, str(payload.get("colour", "#3B82F6"))))
        handler.send_json(201, {"id": cursor.lastrowid})
        return True
    if method == "POST" and path == "/api/templates":
        if not _require(handler):
            return True
        values = shift_pattern_values(connection, payload)
        cursor = connection.execute(
            """INSERT INTO shift_templates
               (location_id,shift_type_id,label,sub_shift_type,start_time,end_time,break_minutes,applicable_days,active)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            values,
        )
        handler.send_json(201, {"id": cursor.lastrowid})
        return True
    if method == "POST" and path.startswith("/api/templates/") and path.endswith("/apply"):
        if not _require(handler):
            return True
        template_id = int(path.split("/")[-2])
        count = app.update_template_in_future_shifts(connection, template_id, payload.get("from_date", date.today().isoformat()))
        handler.send_json(200, {"updated": count})
        return True
    if method == "PUT" and path.startswith("/api/locations/"):
        if not _require(handler):
            return True
        item_id = int(path.rsplit("/", 1)[1])
        from travel_refresh import location_changed
        previous = connection.execute("SELECT address FROM locations WHERE id=?", (item_id,)).fetchone()
        if previous:
            location_changed(connection, previous[0], str(payload.get("address", "")).strip())
        connection.execute("UPDATE locations SET name=?, address=?, active=? WHERE id=?", (str(payload["name"]).strip(), str(payload.get("address", "")).strip(), 1 if payload.get("active", True) else 0, item_id))
        save_location_categories(connection, item_id, payload.get("shift_type_ids"))
        if "colour" in payload:
            connection.execute("UPDATE locations SET colour=? WHERE id=?", (valid_colour(payload["colour"]), item_id))
        connection.commit()
        handler.send_json(200, {"id": item_id})
        return True
    if method == "PUT" and path.startswith("/api/menu-branches/"):
        if not _require(handler):
            return True
        item_id = int(path.rsplit("/", 1)[1])
        current = connection.execute(
            "SELECT branch_key FROM menu_branches WHERE id=?", (item_id,)
        ).fetchone()
        if not current:
            raise ValueError("Menu branch not found.")
        values = branch_values(payload, current["branch_key"])
        connection.execute(
            """UPDATE menu_branches SET title=?,description=?,icon=?,branch_type=?,content=?,active=?,sort_order=?
               WHERE id=?""",
            (*values[1:], item_id),
        )
        connection.commit()
        handler.send_json(200, {"id": item_id})
        return True
    if method == "PUT" and path.startswith("/api/parent-menu-branches/"):
        if not _require(handler):
            return True
        item_id = int(path.rsplit("/", 1)[1])
        current = connection.execute(
            "SELECT branch_key FROM parent_menu_branches WHERE id=?", (item_id,)
        ).fetchone()
        if not current:
            raise ValueError("Parent menu item not found.")
        values = parent_branch_values(payload, current["branch_key"])
        validate_parent_branch(connection, values[8], item_id)
        connection.execute(
            """UPDATE parent_menu_branches SET title=?,description=?,icon=?,destination=?,content=?,active=?,sort_order=?,parent_id=?,colour=?,locked=?,optional=?
               WHERE id=?""", (*values[1:], item_id))
        connection.commit()
        handler.send_json(200, {"id": item_id})
        return True
    if method == "PUT" and path.startswith("/api/shift-types/"):
        if not _require(handler):
            return True
        item_id = int(path.rsplit("/", 1)[1])
        connection.execute("UPDATE shift_types SET name=?, colour=?, active=? WHERE id=?", (str(payload["name"]).strip(), str(payload.get("colour", "#3B82F6")), 1 if payload.get("active", True) else 0, item_id))
        connection.commit()
        handler.send_json(200, {"id": item_id})
        return True
    if method == "PUT" and path.startswith("/api/templates/"):
        if not _require(handler):
            return True
        item_id = int(path.rsplit("/", 1)[1])
        values = shift_pattern_values(connection, payload, exclude_id=item_id)
        connection.execute(
            """UPDATE shift_templates
               SET location_id=?,shift_type_id=?,label=?,sub_shift_type=?,start_time=?,end_time=?,
                   break_minutes=?,applicable_days=?,active=? WHERE id=?""",
            (*values, item_id),
        )
        connection.commit()
        handler.send_json(200, {"id": item_id})
        return True
    return False
