"""Profile settings for the section-driven Align V3 application."""
from __future__ import annotations

import sqlite3
from urllib.parse import urlparse

USER_EDITABLE_SETTINGS = {
    "user_name", "user_address", "default_calendar", "onboarding_completed",
}


def _stored_number(values: dict, key: str, default: str = "0") -> float:
    raw = values.get(key, default)
    if raw is None or str(raw).strip() == "":
        raw = default
    return float(raw)


def get_settings(connection: sqlite3.Connection) -> dict:
    values = {row["setting_key"]: row["setting_value"] for row in connection.execute("SELECT * FROM settings")}
    return {
        **values,
        "user_name": values.get("user_name") or "",
        "user_address": values.get("user_address") or "",
        "contracted_hours": _stored_number(values, "contracted_hours"),
        "rate_of_pay": _stored_number(values, "rate_of_pay"),
        "notifications": (values.get("notifications") or "1") == "1",
        "onboarding_completed": values.get("onboarding_completed", "0") == "1",
        "leave_allowance_days": int(_stored_number(values, "leave_allowance_days")),
        "leave_year_start": values.get("leave_year_start") or "01-01",
        "minimum_rest_hours": _stored_number(values, "minimum_rest_hours"),
    }


def save_settings(connection: sqlite3.Connection, payload: dict, allowed: set[str]) -> dict:
    import app as align

    for key, value in payload.items():
        if key not in allowed:
            continue
        if key in {"contracted_hours", "rate_of_pay"}:
            value = str(float(value))
        if key == "leave_allowance_days":
            number = int(float(value))
            if not 0 <= number <= 366:
                raise ValueError("Leave allowance must be between 0 and 366 days.")
            value = str(number)
        if key == "minimum_rest_hours":
            number = float(value)
            if not 0 <= number <= 24:
                raise ValueError("Minimum rest must be between 0 and 24 hours.")
            value = str(number)
        if key == "leave_year_start":
            value = align.normalise_leave_year_start(value)
        if key in {"notifications", "onboarding_completed"}:
            value = "1" if bool(value) else "0"
        connection.execute(
            "UPDATE settings SET setting_value=? WHERE setting_key=?",
            (str(value).strip(), key),
        )
    settings = get_settings(connection)
    if settings["onboarding_completed"] and not settings["user_name"].strip():
        raise ValueError("Please enter your name before completing setup.")
    return settings


def handle(handler, app, method, connection, payload=None) -> bool:
    path = urlparse(handler.path).path
    if method == "GET" and path == "/api/settings":
        handler.send_json(200, get_settings(connection))
        return True
    if method != "PUT":
        return False
    if path == "/api/user-settings":
        handler.send_json(200, save_settings(connection, payload, USER_EDITABLE_SETTINGS))
        return True
    if path == "/api/settings":
        if not handler.require_admin():
            return True
        handler.send_json(200, save_settings(connection, payload, set(app.DEFAULT_SETTINGS)))
        return True
    return False
