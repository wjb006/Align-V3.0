"""Personal organiser, dashboard, and calendar routes."""
from __future__ import annotations

from datetime import date
from urllib.parse import parse_qs


def handle_get(handler, app, connection, parsed, row) -> bool:
    self = handler
    BETA_MODE = app.BETA_MODE
    BUILD_VERSION = app.BUILD_VERSION
    DATABASE = app.DATABASE
    calendar_data = app.calendar_data
    dashboard = app.dashboard
    find_addresses = app.find_addresses
    get_settings = app.get_settings
    month_data = app.month_data
    navigation_data = app.navigation_data
    organiser_sections = app.organiser_sections
    owner_builder = app.owner_builder
    personal_planner = app.personal_planner
    public_icloud_data = app.public_icloud_data
    if parsed.path == "/api/bootstrap":
        self.send_json(200, {"build_version": BUILD_VERSION, "personal": personal_planner.bootstrap(connection), "builder": owner_builder.bootstrap(DATABASE, connection), "settings": get_settings(connection), "dashboard": dashboard(connection), "calendar": calendar_data(connection), "sections": organiser_sections(connection), "navigation": navigation_data(connection), "icloud_public": public_icloud_data(self.request_icloud_manager(row) if BETA_MODE else None), "icloud_event_calendars": app.icloud_event_calendars(connection), "beta": ({"email":row["email"],"is_owner":bool(row["is_owner"])} if row else None)})
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
    return False


def handle_post(handler, app, connection, path, payload, row) -> bool:
    BETA_MODE = app.BETA_MODE
    import_ics_calendar = app.import_ics_calendar
    self = handler
    if path == "/api/calendars/import":
        source_id, count = import_ics_calendar(
            connection, str(payload.get("name", "")), str(payload.get("ics", ""))
        )
        self.send_json(201, {"id": source_id, "events": count})
        return True
    return False


def handle_put(handler, app, connection, path, payload, row) -> bool:
    return False


def handle_delete(handler, app, connection, path, row) -> bool:
    self = handler
    if path.startswith("/api/calendars/"):
        source_id = int(path.rsplit("/", 1)[1])
        connection.execute("DELETE FROM calendar_sources WHERE id=?", (source_id,))
        self.send_json(200, {"ok": True})
        return True
    return False
