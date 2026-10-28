"""Loopback-only status for the desktop home screen. No secrets and no file paths."""
from __future__ import annotations


def handle_status(handler) -> None:
    client = handler.client_address[0]
    if client not in {"127.0.0.1", "::1"}:
        handler.send_json(403, {"error": "Desktop status is only available on this computer."})
        return
    import app

    database = app.current_database()
    present = False
    try:
        present = database.is_file() and database.stat().st_size > 0
    except OSError:
        present = False
    handler.send_json(200, {
        "surface": "local-desktop",
        "app_version": app.APP_VERSION,
        "build": app.BUILD_VERSION,
        "database_present": present,
        "data_kept_on_this_computer": True,
        "hosted_site": "https://getalign.co.uk",
        "hosted_checked": False,
    })
