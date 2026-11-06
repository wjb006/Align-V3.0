"""Loopback routes for the desktop programme update.

The token is accepted and never returned. These routes do not use git.
"""
from __future__ import annotations

import json
from urllib.parse import urlparse

from desktop.errors import DesktopError
from desktop.paths import user_data_dir
from desktop.update import apply_update, check_for_update, describe, save_preferences, schedule_restart


def _local(handler) -> bool:
    host_header = handler.headers.get("Host", "")
    try:
        hostname = urlparse("//" + host_header).hostname
    except ValueError:
        return False
    if handler.client_address[0] not in {"127.0.0.1", "::1"}:
        return False
    if hostname not in {"127.0.0.1", "localhost", "::1"}:
        return False
    origin = handler.headers.get("Origin")
    if origin not in (None, "", "http://" + host_header):
        return False
    return True


def _body(handler) -> dict:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length < 0 or length > 16_384:
        raise DesktopError("That update request is too large.")
    raw = handler.rfile.read(length) if length else b""
    if not raw:
        return {}
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise DesktopError("That update request could not be read.") from error
    if not isinstance(payload, dict):
        raise DesktopError("That update request could not be read.")
    return payload


def _with_build(payload: dict) -> dict:
    try:
        import app
    except Exception:
        return payload
    payload["build"] = app.BUILD_VERSION
    payload["app_version"] = app.APP_VERSION
    return payload


def handle_update(handler, *, data_dir=None, store=None, transport=None) -> bool:
    path = urlparse(handler.path).path
    routes = {
        "/api/desktop/update",
        "/api/desktop/update/check",
        "/api/desktop/update/apply",
        "/api/desktop/update/restart",
        "/api/desktop/update/settings",
    }
    if path not in routes:
        return False
    if not _local(handler):
        handler.send_json(403, {"error": "Updates are only available on this computer."})
        return True
    folder = data_dir if data_dir is not None else user_data_dir()
    try:
        if handler.command == "POST" and path != "/api/desktop/update/settings":
            _body(handler)
        if path == "/api/desktop/update" and handler.command == "GET":
            handler.send_json(200, _with_build(describe(folder, store)))
            return True
        if path == "/api/desktop/update/check" and handler.command == "POST":
            handler.send_json(200, _with_build(check_for_update(folder, transport=transport, store=store)))
            return True
        if path == "/api/desktop/update/apply" and handler.command == "POST":
            handler.send_json(200, _with_build(apply_update(folder, transport=transport, store=store)))
            return True
        if path == "/api/desktop/update/restart" and handler.command == "POST":
            handler.send_json(200, {"ok": True, "restarting": True, "summary": "Restarting Align to load the update."})
            schedule_restart(handler.server)
            return True
        if path == "/api/desktop/update/settings" and handler.command == "POST":
            payload = _body(handler)
            check_on_launch = payload.get("check_on_launch") if "check_on_launch" in payload else None
            if check_on_launch is not None and not isinstance(check_on_launch, bool):
                raise DesktopError("Choose whether Align checks when it opens.")
            token = payload.get("token") if "token" in payload else None
            if token is not None and not isinstance(token, str):
                raise DesktopError("That GitHub token cannot be saved.")
            saved = save_preferences(folder, check_on_launch=check_on_launch, token=token, store=store)
            result = _with_build(describe(folder, store))
            result.update(saved)
            result.pop("token", None)
            handler.send_json(200, result)
            return True
        handler.send_json(405, {"error": "That update action is not available."})
    except DesktopError as error:
        handler.send_json(400, {"error": str(error)})
    return True
