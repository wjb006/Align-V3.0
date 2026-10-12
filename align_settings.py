"""Profile settings for the section-driven Align V3 application."""
from __future__ import annotations

import sqlite3
from urllib.parse import urlparse

USER_EDITABLE_SETTINGS = {
    "user_name", "user_address", "default_calendar", "onboarding_completed",
}


def get_settings(connection: sqlite3.Connection) -> dict:
    # Legacy schedule values remain stored for recovery, but are never returned
    # to the V3 client, including when opening a pre-V3 database.
    values = {row["setting_key"]: row["setting_value"] for row in connection.execute("SELECT * FROM settings")}
    for key in ("contracted_hours", "standard_shift_minutes", "work_setup_completed",
                "rate_of_pay", "leave_allowance_days", "leave_year_start",
                "minimum_rest_hours", "alert_rules_configured", "work_settings_menu_v122"):
        values.pop(key, None)
    return {
        **values,
        "user_name": values.get("user_name") or "",
        "user_address": values.get("user_address") or "",
        "notifications": (values.get("notifications") or "1") == "1",
        "onboarding_completed": values.get("onboarding_completed", "0") == "1",
    }


def save_settings(connection: sqlite3.Connection, payload: dict, allowed: set[str]) -> dict:
    for key, value in payload.items():
        if key not in allowed:
            continue
        if key == "onboarding_completed":
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
    if method != "PUT" or path != "/api/user-settings":
        return False
    handler.send_json(200, save_settings(connection, payload, USER_EDITABLE_SETTINGS))
    return True
