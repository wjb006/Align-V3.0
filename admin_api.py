"""Local admin session and master-data routes."""
from __future__ import annotations

import re
import secrets
import sqlite3
from http import HTTPStatus
from urllib.parse import urlparse

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


def _require(handler) -> bool:
    return handler.require_admin()


def handle(handler, app, method, connection=None, payload=None) -> bool:
    path = urlparse(handler.path).path

    # Menu-branch admin routes stay retired. Shift locations, types, and
    # templates are served by planner_api.
    retired_schedule_paths = (
        path == "/api/menu-branches"
        or re.fullmatch(r"/api/menu-branches/[0-9]+", path)
        or path == "/api/parent-menu-branches"
        or re.fullmatch(r"/api/parent-menu-branches/[0-9]+", path)
    )
    if retired_schedule_paths:
        handler.send_json(HTTPStatus.NOT_FOUND, {"error": "This schedule-planning endpoint is no longer available."})
        return True

    if method == "GET" and path == "/api/admin/status":
        handler.send_json(200, {"password_required": bool(app.ADMIN_PASSWORD) if not app.BETA_MODE else False, "authenticated": handler.is_admin(), "beta": app.BETA_MODE})
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
    return False
