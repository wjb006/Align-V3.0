"""Local admin session and master-data routes."""
from __future__ import annotations

import re
import secrets
import sqlite3
from http import HTTPStatus
from urllib.parse import urlparse

from colour_utils import colour as valid_colour

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


def _require(handler) -> bool:
    return handler.require_admin()


def handle(handler, app, method, connection=None, payload=None) -> bool:
    path = urlparse(handler.path).path

    # Schedule-planner APIs are retired in Align V3.0. Return an explicit 404
    # before touching legacy tables, including writes from stale clients.
    retired_schedule_paths = (
        path == "/api/locations"
        or re.fullmatch(r"/api/locations/[0-9]+", path)
        or path == "/api/shift-types"
        or re.fullmatch(r"/api/shift-types/[0-9]+", path)
        or path == "/api/templates"
        or re.fullmatch(r"/api/templates/[0-9]+(?:/apply)?", path)
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
    return False
