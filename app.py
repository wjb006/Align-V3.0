"""Align V3.0: a mobile-first personal organiser powered by Python and SQLite.

Run with:  python app.py
Then open: http://127.0.0.1:8001
"""

from __future__ import annotations
import post_event_travel

import json
import hashlib
import logging
import os
import re
import secrets
import socket
import ssl
import sqlite3
from sqlite_support import connect, postgres_enabled
import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from email.utils import format_datetime
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen
from colour_utils import colour as valid_colour
from beta_support import BetaError
import personal_planner
import phone_push
import owner_builder
import migration_runner
import asset_studio
import transport_service
import build152
import health_backup
import align_settings
import organiser_api
import admin_api
import beta_http
import icloud_api
import planner_api

health_status = health_backup.health_status
local_database_backup = health_backup.local_database_backup
local_backup_directory = health_backup.local_backup_directory
restore_local_database = health_backup.restore_local_database
MAX_LOCAL_BACKUP_BYTES = health_backup.MAX_LOCAL_BACKUP_BYTES
get_settings = align_settings.get_settings
save_settings = align_settings.save_settings
USER_EDITABLE_SETTINGS = align_settings.USER_EDITABLE_SETTINGS
organiser_sections = organiser_api.organiser_sections
organiser_section = organiser_api.organiser_section
section_values = organiser_api.section_values
organiser_event_values = organiser_api.organiser_event_values
branch_values = admin_api.branch_values
validate_parent_branch = admin_api.validate_parent_branch
parent_branch_values = admin_api.parent_branch_values
BRANCH_TYPES = admin_api.BRANCH_TYPES
PARENT_DESTINATIONS = admin_api.PARENT_DESTINATIONS

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
DATABASE = ROOT / "align.sqlite3"
BUILD_VERSION = 156
APP_VERSION = "3.0"
BETA_MODE = os.environ.get("ALIGN_BETA_MODE", "0") == "1" or "--beta" in sys.argv
REQUEST_CONTEXT = threading.local()
ICLOUD_MANAGER = None
ICLOUD_MANAGER_LOCK = threading.Lock()
BETA_ICLOUD_MANAGERS: dict[str, object] = {}
BETA_ICLOUD_LOCK = threading.Lock()
BETA_STORE = None
BETA_MAILER = None
LOG = logging.getLogger("align")
EXPECTED_MIGRATIONS = ("149_asset_studio", "149_transport", "150_calendar_links", "151_sections", "152_personal_item_calendars")


def icloud_manager():
    global ICLOUD_MANAGER
    with ICLOUD_MANAGER_LOCK:
        if ICLOUD_MANAGER is None:
            from icloud_sync import ICloudSync
            from types import SimpleNamespace
            ICLOUD_MANAGER = ICloudSync(SimpleNamespace(
                db_connection=db_connection, get_settings=get_settings
            ))
    return ICLOUD_MANAGER
# Set ALIGN_ADMIN_PASSWORD before exposing Align to a home/work network.  When it
# is left unset, the admin page remains convenient for a local single-user setup.
ADMIN_PASSWORD = os.environ.get("ALIGN_ADMIN_PASSWORD", "")
ADMIN_SESSIONS: set[str] = set()
ADDRESS_CACHE: dict[str, tuple[float, list[dict]]] = {}
ADDRESS_LOCK = threading.Lock()
ADDRESS_LAST_REQUEST = 0.0

V3_DEFAULT_SETTINGS = {
    "user_name": "",
    "user_address": "",
    "user_phone": "",
    "user_home_location": "",
    "travel_bus": "true",
    "travel_rail": "true",
    "travel_walk": "true",
    "default_calendar": "Align",
    "notifications": "1",
    "onboarding_completed": "0",
}


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def current_database() -> Path:
    return Path(getattr(REQUEST_CONTEXT, "database", DATABASE))


def db_connection() -> sqlite3.Connection:
    if not postgres_enabled():
        migration_runner.upgrade(current_database())
    connection = connect(current_database(), factory=ClosingConnection)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


class FixedDatabaseApp:
    def __init__(self, database: Path):
        self.database = Path(database)
        # iCloud sync now depends only on retained V3 calendar and settings data.
        self.get_settings = get_settings

    def db_connection(self):
        if not postgres_enabled():
            migration_runner.upgrade(self.database)
        connection = connect(self.database, factory=ClosingConnection)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


def rows_as_dicts(cursor: sqlite3.Cursor) -> list[dict]:
    return [dict(row) for row in cursor.fetchall()]


def valid_iso_date(value: str) -> str:
    return datetime.strptime(value, "%Y-%m-%d").date().isoformat()


def monday_for(value: date) -> date:
    return value - timedelta(days=value.weekday())


def retired_schedule_endpoint(path: str) -> bool:
    """Reject retired schedule routes before opening a database."""
    return bool(
        path in {
            "/api/shifts", "/api/week", "/api/annual-leave", "/api/work-setup",
            "/api/alerts", "/api/shift-completions", "/api/locations",
            "/api/shift-types", "/api/templates",
        }
        or re.fullmatch(r"/api/(?:shifts|annual-leave|alerts|shift-completions)/[0-9]+", path)
        or re.fullmatch(r"/api/(?:locations|shift-types)/[0-9]+", path)
        or re.fullmatch(r"/api/templates/[0-9]+(?:/apply)?", path)
    )


def reject_retired_schedule_endpoint(handler) -> bool:
    """Return a consistent 404 for retired schedule routes without DB access."""
    path = urlparse(handler.path).path
    if not retired_schedule_endpoint(path):
        return False
    handler.send_json(HTTPStatus.NOT_FOUND, {"error": "This schedule-planning endpoint is no longer available."})
    return True


def initialise_database_at(database: Path) -> None:
    if postgres_enabled():
        from postgres_support import validate_v3_storage
        with connect(database) as connection:
            validate_v3_storage(connection)
        return
    database = Path(database)
    database.parent.mkdir(parents=True, exist_ok=True)
    legacy_schema = False
    if database.exists() and database.stat().st_size:
        with sqlite3.connect(str(database)) as probe:
            legacy_schema = bool(probe.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name IN "
                "('shifts','shift_templates','shift_types','locations','location_shift_types',"
                "'annual_leave','alert_rules','alerts','shift_batches') LIMIT 1"
            ).fetchone())
    if not legacy_schema:
        schema = (ROOT / "schema_v3.sqlite.sql").read_text(encoding="utf-8")
        connection = connect(database, factory=ClosingConnection)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            connection.executescript(schema)
            connection.executemany(
                "INSERT OR IGNORE INTO settings(setting_key, setting_value) VALUES (?, ?)",
                V3_DEFAULT_SETTINGS.items(),
            )
            connection.execute(
                "UPDATE icloud_config SET instance_id=? WHERE id=1 AND instance_id=''",
                (secrets.token_hex(16),),
            )
        return
    schema = (ROOT / "schema.sql").read_text(encoding="utf-8")
    migration_runner.upgrade(database)
    connection = connect(database, factory=ClosingConnection)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    with connection:
        connection.executescript(schema)
        connection.execute("UPDATE icloud_config SET instance_id=? WHERE id=1 AND instance_id=''", (secrets.token_hex(16),))
        if 'colour' not in {row['name'] for row in connection.execute('PRAGMA table_info(locations)')}:
            connection.execute("ALTER TABLE locations ADD COLUMN colour TEXT NOT NULL DEFAULT '#365CE6'")
        calendar_source_columns = {row['name'] for row in connection.execute('PRAGMA table_info(calendar_sources)')}
        if 'section_id' not in calendar_source_columns:
            connection.execute('ALTER TABLE calendar_sources ADD COLUMN section_id INTEGER REFERENCES organiser_sections(id) ON DELETE CASCADE')
        if 'source_key' not in calendar_source_columns:
            connection.execute("ALTER TABLE calendar_sources ADD COLUMN source_key TEXT NOT NULL DEFAULT ''")
        if 'location' not in {row['name'] for row in connection.execute('PRAGMA table_info(calendar_events)')}:
            connection.execute("ALTER TABLE calendar_events ADD COLUMN location TEXT NOT NULL DEFAULT ''")
        organiser_event_columns = {row['name'] for row in connection.execute('PRAGMA table_info(organiser_events)')}
        if 'request_id' not in organiser_event_columns:
            connection.execute('ALTER TABLE organiser_events ADD COLUMN request_id TEXT')
            connection.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_organiser_events_request ON organiser_events(request_id) WHERE request_id IS NOT NULL')
        parent_columns = {row['name'] for row in connection.execute('PRAGMA table_info(parent_menu_branches)')}
        if 'parent_id' not in parent_columns:
            connection.execute('ALTER TABLE parent_menu_branches ADD COLUMN parent_id INTEGER REFERENCES parent_menu_branches(id) ON DELETE SET NULL')
        if 'colour' not in parent_columns:
            connection.execute("ALTER TABLE parent_menu_branches ADD COLUMN colour TEXT NOT NULL DEFAULT '#365CE6'")
        if 'locked' not in parent_columns:
            connection.execute('ALTER TABLE parent_menu_branches ADD COLUMN locked INTEGER NOT NULL DEFAULT 0')
        if 'optional' not in parent_columns:
            connection.execute('ALTER TABLE parent_menu_branches ADD COLUMN optional INTEGER NOT NULL DEFAULT 1')
        section_columns = {row['name'] for row in connection.execute('PRAGMA table_info(organiser_sections)')}
        if 'parent_branch_id' not in section_columns:
            connection.execute('ALTER TABLE organiser_sections ADD COLUMN parent_branch_id INTEGER REFERENCES parent_menu_branches(id) ON DELETE SET NULL')
        connection.execute('CREATE INDEX IF NOT EXISTS idx_parent_menu_tree ON parent_menu_branches(active,parent_id,sort_order,title)')
        # Keep calendar revision tracking for retained V3 settings only. Legacy
        # schedule/leave rows are preserved as archival data and never rewritten.
        connection.execute("""CREATE TRIGGER IF NOT EXISTS sync_calendar_settings
            AFTER UPDATE ON settings
            WHEN NEW.setting_key IN ('notifications','default_calendar')
            BEGIN UPDATE calendar_sync_state SET revision=revision+1,
                modified_at=strftime('%Y%m%dT%H%M%SZ','now') WHERE id=1; END""")
        connection.executemany(
            "INSERT OR IGNORE INTO settings(setting_key, setting_value) VALUES (?, ?)",
            V3_DEFAULT_SETTINGS.items(),
        )
    migration_runner.upgrade_planner_schema(database)



def initialise_database() -> None:
    initialise_database_at(DATABASE)


def beta_store():
    global BETA_STORE
    if BETA_STORE is None:
        from beta_support import BetaStore
        BETA_STORE = BetaStore(ROOT, DATABASE, initialise_database_at)
    return BETA_STORE


def beta_mailer():
    global BETA_MAILER
    if BETA_MAILER is None:
        from beta_email import BetaMailer
        BETA_MAILER = BetaMailer(beta_store())
    return BETA_MAILER


def apply_owner_template_to_database(target: Path) -> None:
    """Copy only structure/default containers; never copy owner planner content."""
    initialise_database_at(target)
    with connect(DATABASE) as source, connect(target) as dest:
        source.row_factory = sqlite3.Row
        dest.execute('PRAGMA foreign_keys=ON')
        # Defaults/settings useful to a new tester, but never name/address/pay/calendar.
        safe_settings = {**V3_DEFAULT_SETTINGS}
        for key,value in safe_settings.items():
            dest.execute('UPDATE settings SET setting_value=? WHERE setting_key=?',(value,key))
        # Replace the parent tree, preserving hierarchy through branch_key mapping.
        dest.execute('DELETE FROM parent_menu_branches')
        rows=[dict(r) for r in source.execute('SELECT * FROM parent_menu_branches ORDER BY sort_order,id')]
        old_by_id={r['id']:r for r in rows}; new_by_key={}
        pending=rows[:]
        while pending:
            progressed=False
            for r in pending[:]:
                parent=r.get('parent_id')
                parent_key=old_by_id.get(parent,{}).get('branch_key') if parent else None
                if parent_key and parent_key not in new_by_key: continue
                cur=dest.execute("""INSERT INTO parent_menu_branches(branch_key,title,description,icon,destination,content,active,sort_order,parent_id,colour,locked,optional)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",(r['branch_key'],r['title'],r['description'],r['icon'],r['destination'],r['content'],r['active'],r['sort_order'],new_by_key.get(parent_key),r.get('colour','#365CE6'),r.get('locked',0),r.get('optional',1)))
                new_by_key[r['branch_key']]=cur.lastrowid; pending.remove(r); progressed=True
            if not progressed: break
        # Starter organiser sections are empty containers only; no calendar URLs/events.
        dest.execute('DELETE FROM organiser_sections')
        for r in source.execute('SELECT * FROM organiser_sections WHERE active=1 ORDER BY sort_order,id'):
            parent_key=old_by_id.get(r['parent_branch_id'],{}).get('branch_key') if 'parent_branch_id' in r.keys() and r['parent_branch_id'] else None
            dest.execute("""INSERT INTO organiser_sections(name,description,icon,colour,calendar_url,calendar_name,import_enabled,export_enabled,active,sort_order,parent_branch_id)
                VALUES(?,?,?,?, '', '', ?,?,?,?,?)""",(r['name'],r['description'],r['icon'],r['colour'],r['import_enabled'],r['export_enabled'],r['active'],r['sort_order'],new_by_key.get(parent_key)))


def beta_icloud_manager(row, restore: bool=True):
    from icloud_sync import ICloudSync
    store=beta_store(); uid=row['user_id']
    with BETA_ICLOUD_LOCK:
        manager=BETA_ICLOUD_MANAGERS.get(uid)
        if manager is None:
            manager=ICloudSync(FixedDatabaseApp(store.database_for(row)))
            BETA_ICLOUD_MANAGERS[uid]=manager
            if restore:
                try:
                    saved=store.load_icloud(row)
                except BetaError as exc:
                    if exc.code not in ('credential_error', 'credential_key_unavailable'): raise
                    manager.reconnect_required = True
                    manager.message = 'Reconnect iCloud in Calendar settings. Your saved planner and calendar data are still available.'
                else:
                    if saved:
                        try: manager.resume(*saved)
                        except Exception:
                            manager.message = 'iCloud is temporarily unavailable. Retry from Calendar settings.'
        return manager


def restore_all_beta_icloud():
    if not BETA_MODE: return
    for row in beta_store().list_users():
        try:
            live=beta_store().user(row['user_id'])
            if live and live['active'] and row.get('icloud_saved'): beta_icloud_manager(live, True)
        except Exception:
            pass

def normalise_leave_year_start(value) -> str:
    text = str(value or "").strip()
    if not re.fullmatch(r"(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])", text):
        raise ValueError("Leave year start must be a month and day, such as 04-01.")
    month, day = int(text[:2]), int(text[3:])
    if month == 2 and day == 29:
        return "02-29"
    try:
        date(2023, month, day)
    except ValueError as error:
        raise ValueError("Leave year start must be a real month and day, such as 04-01.") from error
    return f"{month:02d}-{day:02d}"


def find_addresses(query: str) -> list[dict]:
    """Small, rate-limited UK address lookup with manual-entry fallback in the UI."""
    global ADDRESS_LAST_REQUEST
    query = " ".join(query.split())[:120]
    if len(query) < 3:
        raise ValueError("Enter at least three characters to search for an address.")
    cache_key = query.casefold()
    cached = ADDRESS_CACHE.get(cache_key)
    if cached and time.monotonic() - cached[0] < 600:
        return cached[1]
    with ADDRESS_LOCK:
        cached = ADDRESS_CACHE.get(cache_key)
        if cached and time.monotonic() - cached[0] < 600:
            return cached[1]
        delay = 1.0 - (time.monotonic() - ADDRESS_LAST_REQUEST)
        if delay > 0:
            time.sleep(delay)
        url = "https://nominatim.openstreetmap.org/search?" + urlencode({
            "q": query, "format": "jsonv2", "addressdetails": "1", "limit": 8, "countrycodes": "gb", "accept-language":"en-GB", "dedupe":"1",
        })
        request = Request(url, headers={"User-Agent": "AlignShiftPlanner/1.0 (personal local planner)"})
        try:
            with urlopen(request, timeout=6) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except OSError as error:
            raise ValueError("Address search is unavailable right now. You can type the address manually.") from error
        ADDRESS_LAST_REQUEST = time.monotonic()
        priority={'house':0,'building':0,'residential':1,'postcode':1,'road':2,'street':2,'amenity':2,'office':2,'shop':2}
        payload.sort(key=lambda item:(priority.get(str(item.get('type','')).lower(),5),-float(item.get('importance') or 0)))
        results=[{'label':item.get('display_name',''),'latitude':item.get('lat',''),'longitude':item.get('lon',''),'postcode':(item.get('address') or {}).get('postcode',''),'country_code':(item.get('address') or {}).get('country_code','gb')} for item in payload if item.get('display_name')][:8]
        ADDRESS_CACHE[cache_key] = (time.monotonic(), results)
        return results


def master_data(connection: sqlite3.Connection, include_inactive: bool = False) -> dict:
    """Compatibility response for old clients; V3 no longer exposes shift setup."""
    branch_where = "" if include_inactive else " WHERE active = 1"
    branches = rows_as_dicts(connection.execute(
        f"SELECT * FROM menu_branches{branch_where} ORDER BY sort_order, title"
    ))
    parents = rows_as_dicts(connection.execute(
        f"SELECT p.*, parent.title AS parent_title FROM parent_menu_branches p "
        f"LEFT JOIN parent_menu_branches parent ON parent.id=p.parent_id"
        f"{branch_where.replace('active','p.active')} "
        "ORDER BY COALESCE(p.parent_id,0),p.sort_order,p.title"
    ))
    return {"locations": [], "shift_types": [], "templates": [],
            "location_categories": {}, "branches": branches, "parents": parents}



def public_icloud_data(manager=None) -> dict:
    manager = manager if manager is not None else ICLOUD_MANAGER
    if manager is None or manager.client is None:
        return {'connected': False, 'enabled': False, 'calendars': [], 'reconnect_required': bool(getattr(manager, 'reconnect_required', False)), 'message': getattr(manager, 'message', 'Connect iCloud from PC Admin to link calendars.')}
    with manager.lock:
        return {'connected': True, 'enabled': manager.enabled,
                'calendars': list(manager.options), 'message': manager.message, 'last_sync': manager.last_sync}


def icloud_event_calendars(connection: sqlite3.Connection) -> list[dict]:
    """Return user-selected destinations for new events and calendar sections."""
    return rows_as_dicts(connection.execute(
        "SELECT target_key AS id,calendar_name AS name FROM calendar_links "
        "WHERE target_kind='icloud_calendar' ORDER BY calendar_name"
    ))


def save_icloud_event_calendars(calendar_ids, manager=None) -> dict:
    if not isinstance(calendar_ids, list) or len(calendar_ids) > 100 or any(
        not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{64}', value) for value in calendar_ids
    ):
        raise ValueError('Select valid calendars from your connected iCloud account.')
    manager = manager or icloud_manager()
    if not manager.client:
        raise ValueError('Connect iCloud before selecting calendars.')
    available = {item['id']: item for item in manager.options}
    selected = list(dict.fromkeys(calendar_ids))
    if any(value not in available for value in selected):
        raise ValueError('Refresh your iCloud connection and select calendars from your current account.')
    with db_connection() as connection:
        existing = {row['target_key'] for row in connection.execute(
            "SELECT target_key FROM calendar_links WHERE target_kind='icloud_calendar'"
        )}
        removed = existing - set(selected)
        if removed:
            connection.executemany(
                "DELETE FROM calendar_links WHERE target_kind='icloud_calendar' AND target_key=?",
                [(value,) for value in removed],
            )
        for value in selected:
            calendar = available[value]
            url, name = manager.resolve_calendar(value)
            connection.execute("""INSERT INTO calendar_links
                (target_kind,target_key,calendar_url,calendar_name,import_enabled,export_enabled)
                VALUES('icloud_calendar',?,?,?,1,1)
                ON CONFLICT(target_kind,target_key) DO UPDATE SET
                calendar_url=excluded.calendar_url,calendar_name=excluded.calendar_name""",
                (value, url, name or calendar['name']))
            from organiser_api import event_section_for_calendar
            event_section_for_calendar(connection, value)
        return {'calendars': icloud_event_calendars(connection)}


def month_data(connection: sqlite3.Connection, month: str) -> dict:
    if not re.fullmatch(r'\d{4}-\d{2}', month):
        raise ValueError('Choose a month in YYYY-MM format.')
    first = date.fromisoformat(month + '-01')
    following = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    last = following - timedelta(days=1)
    start = monday_for(first)
    end = monday_for(last) + timedelta(days=6)
    return {'month': month, 'start': start.isoformat(), 'end': end.isoformat(),
            'events': rows_as_dicts(connection.execute('SELECT oe.id,oe.section_id,oe.title,oe.start_at,oe.end_at,oe.all_day,oe.location,oe.notes,os.colour AS section_colour FROM organiser_events oe LEFT JOIN organiser_sections os ON os.id=oe.section_id WHERE oe.start_at<? AND oe.end_at>? ORDER BY oe.start_at', ((end+timedelta(days=1)).isoformat(), start.isoformat()))),
            'imported_events': rows_as_dicts(connection.execute('SELECT ce.id,cs.section_id,ce.title,ce.start_at,ce.end_at,ce.all_day,ce.location,cs.name AS category_name,os.colour AS section_colour FROM calendar_events ce JOIN calendar_sources cs ON cs.id=ce.source_id LEFT JOIN organiser_sections os ON os.id=cs.section_id WHERE ce.start_at<? AND ce.end_at>? ORDER BY ce.start_at', ((end+timedelta(days=1)).isoformat(), start.isoformat()))),
            }



def calendar_data(connection: sqlite3.Connection) -> dict:
    sources = rows_as_dicts(connection.execute(
        """SELECT s.*, COUNT(e.id) AS event_count
           FROM calendar_sources s LEFT JOIN calendar_events e ON e.source_id=s.id
           GROUP BY s.id ORDER BY s.name"""
    ))
    sync = dict(connection.execute("SELECT revision,modified_at FROM calendar_sync_state WHERE id=1").fetchone())
    return {"sources": sources, "align_calendar_name": "Align",
            "feed_path": "/api/calendars/live.ics", "sync": sync,
            "alert_rules": []}


def parse_ics_date(raw: str) -> tuple[datetime, bool]:
    raw = raw.strip()
    if re.fullmatch(r"\d{8}", raw):
        return datetime.strptime(raw, "%Y%m%d"), True
    raw = raw.rstrip("Z")
    for format_string in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M"):
        try:
            return datetime.strptime(raw, format_string), False
        except ValueError:
            continue
    raise ValueError("An imported calendar contains an unreadable date.")


def import_ics_calendar(connection: sqlite3.Connection, name: str, ics: str) -> tuple[int, int]:
    name = name.strip()[:120] or "Imported calendar"
    if len(ics) > 1_000_000:
        raise ValueError("Calendar file is too large.")
    unfolded = re.sub(r"\r?\n[ \t]", "", ics)
    blocks = re.findall(r"BEGIN:VEVENT\s*(.*?)\s*END:VEVENT", unfolded, re.DOTALL | re.IGNORECASE)
    if not blocks:
        raise ValueError("No calendar events were found in that .ics file.")
    events = []
    for block in blocks:
        values: dict[str, str] = {}
        for line in block.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.split(";", 1)[0].upper()
            if key in {"UID", "DTSTART", "DTEND", "SUMMARY", "LOCATION"}:
                values[key] = value.replace("\\,", ",").replace("\\n", " ").strip()
        if "DTSTART" not in values:
            continue
        start, all_day = parse_ics_date(values["DTSTART"])
        end, _ = parse_ics_date(values.get("DTEND", values["DTSTART"]))
        if end <= start:
            end = start + timedelta(days=1 if all_day else 1 / 24)
        events.append((values.get("UID", secrets.token_hex(12)), start.isoformat(timespec="minutes"),
                       end.isoformat(timespec="minutes"), values.get("SUMMARY", "Imported calendar event"), 1 if all_day else 0, values.get("LOCATION", "")[:1000]))
    if not events:
        raise ValueError("No usable calendar events were found in that .ics file.")
    cursor = connection.execute("INSERT INTO calendar_sources(name,source_kind) VALUES(?, 'ics_import')", (name,))
    source_id = cursor.lastrowid
    connection.executemany(
        "INSERT OR IGNORE INTO calendar_events(source_id,event_uid,start_at,end_at,title,all_day,location) VALUES(?,?,?,?,?,?,?)",
        [(source_id, *event) for event in events],
    )
    ensure_import_categories(connection)
    return source_id, len(events)


def ensure_import_categories(connection):
    for source in connection.execute("SELECT id,name FROM calendar_sources WHERE section_id IS NULL AND source_kind='ics_import'").fetchall():
        existing = connection.execute("SELECT id FROM organiser_sections WHERE calendar_name=? AND calendar_url='' AND description='Imported calendar events'", (source['name'],)).fetchone()
        section_id = existing['id'] if existing else connection.execute(
            "INSERT INTO organiser_sections(name,calendar_name,description,icon,export_enabled) VALUES(?,?,'Imported calendar events','▦',0)",
            (source['name'], source['name'])).lastrowid
        connection.execute('UPDATE calendar_sources SET section_id=? WHERE id=?', (section_id, source['id']))


def ics_escape(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold_ics_line(line: str) -> str:
    parts, current = [], ""
    for char in line:
        if len((current + char).encode("utf-8")) > 75:
            parts.append(current)
            current = " "
        current += char
    parts.append(current)
    return "\r\n".join(parts)


def align_ics(connection: sqlite3.Connection) -> bytes:
    sync = connection.execute("SELECT * FROM calendar_sync_state WHERE id=1").fetchone()
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Align//Align Calendar//EN", "CALSCALE:GREGORIAN",
             "X-WR-CALNAME:Align", "X-WR-TIMEZONE:Europe/London",
             "REFRESH-INTERVAL;VALUE=DURATION:PT15M", "X-PUBLISHED-TTL:PT15M",
             "BEGIN:VTIMEZONE", "TZID:Europe/London",
             "BEGIN:DAYLIGHT", "DTSTART:19960331T010000", "TZOFFSETFROM:+0000", "TZOFFSETTO:+0100",
             "TZNAME:BST", "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU", "END:DAYLIGHT",
             "BEGIN:STANDARD", "DTSTART:19961027T020000", "TZOFFSETFROM:+0100", "TZOFFSETTO:+0000",
             "TZNAME:GMT", "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU", "END:STANDARD", "END:VTIMEZONE"]
    revision_lines = [f"DTSTAMP:{sync['modified_at']}", f"LAST-MODIFIED:{sync['modified_at']}", f"SEQUENCE:{sync['revision']}"]
    # The Align subscription now exports the event records created through
    # Sections. Legacy shift and annual-leave rows stay in their tables for
    # backup/recovery, but are no longer published as part of the V3 calendar.
    for event in connection.execute(
        "SELECT id,title,start_at,end_at,all_day,location,notes FROM organiser_events ORDER BY start_at,id"
    ):
        start = datetime.fromisoformat(event["start_at"])
        end = datetime.fromisoformat(event["end_at"])
        lines.extend(["BEGIN:VEVENT", f"UID:align-event-{event['id']}@getalign.co.uk", *revision_lines])
        if event["all_day"]:
            lines.extend([f"DTSTART;VALUE=DATE:{start.strftime('%Y%m%d')}",
                          f"DTEND;VALUE=DATE:{end.strftime('%Y%m%d')}"])
        else:
            lines.extend([f"DTSTART;TZID=Europe/London:{start.strftime('%Y%m%dT%H%M%S')}",
                          f"DTEND;TZID=Europe/London:{end.strftime('%Y%m%dT%H%M%S')}"])
        lines.extend(["STATUS:CONFIRMED", f"SUMMARY:{ics_escape(event['title'])}"])
        if event["location"]:
            lines.append(f"LOCATION:{ics_escape(event['location'])}")
        if event["notes"]:
            lines.append(f"DESCRIPTION:{ics_escape(event['notes'])}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return ("\r\n".join(fold_ics_line(line) for line in lines) + "\r\n").encode("utf-8")


def dashboard(connection: sqlite3.Connection) -> dict:
    now = datetime.now(ZoneInfo('Europe/London'))
    today = now.date().isoformat()
    from post_event_travel import instant
    upcoming_events = rows_as_dicts(connection.execute(
        """SELECT oe.id,oe.section_id,oe.title,oe.start_at,oe.end_at,oe.all_day,oe.location,oe.notes,
                  os.name AS category_name, os.colour AS section_colour, 'Event' AS origin
           FROM organiser_events oe
           LEFT JOIN organiser_sections os ON os.id=oe.section_id
           WHERE oe.end_at >= ? ORDER BY oe.start_at""", (today,)
    ))
    upcoming_events += rows_as_dicts(connection.execute(
        """SELECT ce.id,cs.section_id,ce.title,ce.start_at,ce.end_at,ce.all_day,ce.location,
                  cs.name AS category_name, os.colour AS section_colour, '' AS notes, 'Calendar' AS origin
           FROM calendar_events ce
           JOIN calendar_sources cs ON cs.id=ce.source_id
           LEFT JOIN organiser_sections os ON os.id=cs.section_id
           WHERE ce.end_at>=?""", (today,)))
    upcoming_events = sorted((e for e in upcoming_events if instant(e['end_at']) > now), key=lambda e: instant(e['start_at']))[:50]
    post_event_travel.decorate(connection, upcoming_events)
    return {
        "today": today,
        # Keep legacy response keys empty for older installed clients while
        # removing the shift/leave planner from the active V3 experience.
        "week_start": "",
        "upcoming": [],
        "upcoming_events": upcoming_events,
        "annual_leave": [],
        "leave_balance": None,
        "alerts": [],
        "reminder_alerts": [],
        "summary": week_hours_summary([], 0, 0),
    }


class AlignHandler(SimpleHTTPRequestHandler):
    """Static front-end and a deliberately small JSON API."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def log_message(self, fmt, *args):
        request_line = str(args[0]) if args else ""
        match = re.match(r"^([A-Z]+)\s+(\S+)\s+HTTP/\d(?:\.\d)?$", request_line)
        if match:
            path = urlparse(match.group(2)).path[:256]
            status = args[1] if len(args) > 1 else ""
            size = args[2] if len(args) > 2 else ""
            LOG.info('%s "%s %s" %s %s', self.log_date_time_string(), match.group(1), path, status, size)
        else:
            LOG.info("%s HTTP request event", self.log_date_time_string())

    def end_headers(self):
        path = urlparse(getattr(self, "path", "")).path
        # Safari/PWA upgrades must always revalidate the application entry point
        # and worker while the PC is reachable. Offline availability comes from
        # Align's own service-worker cache, not the browser HTTP cache.
        auth_pages = {
            "/beta-login", "/beta-login.html", "/beta-invite", "/beta-invite.html",
            "/beta-forgot", "/beta-forgot.html", "/beta-reset", "/beta-reset.html",
            "/beta-terms", "/beta-terms.html", "/beta-welcome", "/beta-welcome.html",
            "/login", "/login.html", "/invite", "/invite.html",
            "/forgot", "/forgot.html", "/reset", "/reset.html",
            "/terms", "/terms.html", "/welcome", "/welcome.html",
            "/account", "/account.html",
        }
        if not path.startswith("/api/") and (path in {
            "/", "/index.html", "/admin", "/admin.html",
            "/service-worker.js", "/manifest.json",
        } or path in auth_pages):
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
        if BETA_MODE and (path.endswith(".js") or path.endswith(".css")):
            # Beta testers must receive frontend fixes on refresh without
            # restarting the long-lived beta process.
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
        # Baseline headers on every HTML, static, and API response. Referrer-Policy
        # stays no-referrer, which is what beta auth pages already sent.
        # script-src does not allow 'unsafe-inline': pages load external scripts.
        # style-src still allows 'unsafe-inline' because shared pages use <style>
        # blocks and style attributes. Moving those out is a separate visual change.
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; worker-src 'self'; manifest-src 'self'; "
            "base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'",
        )
        if path == "/service-worker.js":
            self.send_header("Service-Worker-Allowed", "/")
        super().end_headers()

    def send_json(self, status: int, payload: dict | list) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # GET responses may be stored by Align's private service-worker cache for offline use.
        # Mutating/API login responses remain non-storable.
        self.send_header("Cache-Control", ("no-store" if self.path.startswith("/api/health") or (BETA_MODE and ("/api/beta/" in self.path or "/api/icloud/" in self.path)) else ("private, no-cache" if self.command == "GET" else "no-store")))
        self.end_headers()
        self.wfile.write(body)

    def send_beta_error(self, error: BetaError) -> None:
        payload = {"error": error.code, "message": str(error)}
        if error.retry_after:
            payload["retry_after_seconds"] = int(error.retry_after)
        body = json.dumps(payload).encode("utf-8")
        self.send_response(int(error.status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if error.retry_after:
            self.send_header("Retry-After", str(int(error.retry_after)))
        self.end_headers()
        self.wfile.write(body)

    def beta_base_url(self) -> str:
        configured = os.environ.get('ALIGN_PUBLIC_URL', '').strip().rstrip('/')
        if configured:
            public = urlparse(configured)
            if public.scheme in {'http', 'https'} and public.netloc and not public.username and not public.password:
                return configured
        host = self.headers.get('Host','').strip()
        forwarded = self.headers.get('X-Forwarded-Proto','').split(',')[0].strip().lower()
        scheme = forwarded or ('https' if isinstance(self.connection, ssl.SSLSocket) else 'http')
        return f"{scheme}://{host}".rstrip('/')

    def send_bytes(self, status: int, body: bytes, content_type: str, filename: str | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(body)

    def send_calendar(self, connection: sqlite3.Connection, download: bool = False, head: bool = False) -> None:
        body = align_ics(connection)
        etag = '"' + hashlib.sha256(body).hexdigest() + '"'
        if not download and self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", "no-cache, must-revalidate")
            self.end_headers()
            return
        modified = connection.execute("SELECT modified_at FROM calendar_sync_state WHERE id=1").fetchone()[0]
        modified_at = datetime.strptime(modified, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        self.send_response(200)
        self.send_header("Content-Type", "text/calendar; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("ETag", etag)
        self.send_header("Last-Modified", format_datetime(modified_at, usegmt=True))
        self.send_header("Cache-Control", "no-cache, must-revalidate")
        if download:
            self.send_header("Content-Disposition", 'attachment; filename="align-calendar.ics"')
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def do_HEAD(self):
        path = urlparse(self.path).path
        if path in {"/api/calendars/live.ics", "/api/calendars/align.ics"}:
            with db_connection() as connection:
                self.send_calendar(connection, download=path.endswith("/align.ics"), head=True)
            return
        super().do_HEAD()

    def read_json(self) -> dict:
        if hasattr(self, '_builder_body'):
            body = self._builder_body
            del self._builder_body
            return json.loads(body or b'{}')
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1_000_000:
            raise ValueError("Request is too large.")
        return json.loads(self.rfile.read(length) or b"{}")

    def is_admin(self) -> bool:
        """Owner account is Admin in beta; local builds keep the existing token model."""
        if BETA_MODE:
            row=self.beta_user()
            return bool(row and row['is_owner'] and beta_store().terms_current(row))
        if not ADMIN_PASSWORD: return True
        return self.headers.get("X-Align-Admin", "") in ADMIN_SESSIONS

    def require_admin(self) -> bool:
        if self.is_admin():
            return True
        self.send_json(HTTPStatus.FORBIDDEN, {"error": "Admin sign-in is required for this change."})
        return False

    def require_local_backup_admin(self) -> bool:
        if BETA_MODE or postgres_enabled():
            self.send_json(HTTPStatus.FORBIDDEN, {"error": "Database downloads and restores are disabled in hosted mode."})
            return False
        return self.require_admin()

    def require_local_icloud_admin(self) -> bool:
        if BETA_MODE:
            return bool(self.require_beta_user() and self.beta_same_origin())
        host = self.headers.get('Host', '')
        parsed = urlparse('//' + host)
        scheme = 'https' if isinstance(self.connection, ssl.SSLSocket) else 'http'
        port = self.server.server_address[1]
        local_admin_url = f'{scheme}://127.0.0.1:{port}/admin'
        if self.client_address[0] not in ('127.0.0.1','::1') or parsed.hostname not in ('127.0.0.1','localhost','::1'):
            self.send_json(403, {'error':f'Connect iCloud from the Admin page on this PC using {local_admin_url}.'})
            return False
        if self.headers.get('Origin') not in (None, f'{scheme}://{host}'):
            self.send_json(403, {'error':f'Open {local_admin_url} on this PC before connecting iCloud.'})
            return False
        if self.command == 'POST' and self.headers.get('Content-Type','').split(';')[0] != 'application/json':
            self.send_json(415, {'error':'JSON is required.'})
            return False
        return self.require_admin()

    def beta_cookie_token(self) -> str:
        # Read our cookie defensively. Embedded/mobile browsers can add cookies
        # that Python's SimpleCookie rejects as a whole; one unrelated malformed
        # value must not make Align forget an otherwise valid beta session.
        raw = self.headers.get('Cookie','') or ''
        for part in raw.split(';'):
            name, sep, value = part.strip().partition('=')
            if sep and name == 'align_beta':
                return value.strip()
        cookie = SimpleCookie()
        try:
            cookie.load(raw)
        except Exception:
            return ''
        morsel = cookie.get('align_beta')
        return morsel.value if morsel else ''

    def beta_user(self):
        if not BETA_MODE: return None
        return beta_store().by_session(self.beta_cookie_token())

    def activate_beta_database(self, allow_terms_pending: bool=False) -> object | None:
        if not BETA_MODE: return None
        row=self.beta_user()
        if not row: return None
        if not allow_terms_pending and not beta_store().terms_current(row): return None
        REQUEST_CONTEXT.database=beta_store().database_for(row)
        return row

    def clear_request_database(self):
        if hasattr(REQUEST_CONTEXT,'database'): del REQUEST_CONTEXT.database

    def require_beta_user(self, allow_terms_pending: bool=False) -> object | None:
        if not BETA_MODE: return True
        row=self.activate_beta_database(allow_terms_pending)
        if row: return row
        known=self.beta_user()
        if known and not beta_store().terms_current(known):
            self.send_json(403,{'error':'Accept the current Terms & Privacy Notice first.','code':'terms_required'})
        else:
            self.send_json(401,{'error':'Sign-in is required.','code':'beta_login'})
        return None

    def activate_user_database(self):
        """Select the signed-in account's private database without granting owner rights."""
        if not BETA_MODE:
            return True
        row = self.activate_beta_database()
        if row:
            return row
        self.send_json(401, {'error': 'Sign-in is required.', 'code': 'beta_login'})
        return None

    def beta_same_origin(self) -> bool:
        """Protect beta writes across local and Cloudflare reverse-proxy use.

        Prefer an exact authority comparison, but account for reverse proxies that
        rewrite Host and for browsers that normalise/default ports differently.
        As a browser-enforced fallback, Sec-Fetch-Site: same-origin is accepted.
        Cross-site and same-site (different-host) requests remain rejected.
        """
        def normalise_authority(value: str, scheme_hint: str = '') -> str:
            raw = (value or '').split(',')[0].strip()
            if not raw:
                return ''
            try:
                if '://' in raw:
                    parsed = urlparse(raw)
                    scheme = (parsed.scheme or scheme_hint).lower()
                else:
                    parsed = urlparse('//' + raw)
                    scheme = scheme_hint.lower()
                host = (parsed.hostname or '').rstrip('.').casefold()
                if not host:
                    return ''
                try:
                    port = parsed.port
                except ValueError:
                    return ''
                if port and not ((scheme == 'https' and port == 443) or (scheme == 'http' and port == 80)):
                    return f'{host}:{port}'
                return host
            except Exception:
                return ''

        origin = (self.headers.get('Origin') or '').strip()
        fetch_site = (self.headers.get('Sec-Fetch-Site') or '').strip().lower()

        # Browser-generated Sec-Fetch-Site cannot be set by page JavaScript.
        # It solves the reverse-proxy case where cloudflared rewrites Host while
        # Safari still correctly identifies the request as same-origin.
        if fetch_site == 'same-origin':
            return True

        # Older browsers may omit Origin on some same-origin requests. Preserve
        # compatibility while still rejecting explicit cross-site requests below.
        if not origin:
            return True

        try:
            parsed_origin = urlparse(origin)
        except Exception:
            parsed_origin = None
        if not parsed_origin or parsed_origin.scheme not in ('http', 'https') or not parsed_origin.netloc:
            self.send_json(403, {'error':'This beta request must come from the current Align site.'})
            return False

        origin_authority = normalise_authority(origin)
        allowed_authorities = set()

        # Cloudflare/current proxy host variants.
        for header_name in ('Host', 'X-Forwarded-Host', 'X-Original-Host'):
            raw = self.headers.get(header_name) or ''
            authority = normalise_authority(raw, parsed_origin.scheme)
            if authority:
                allowed_authorities.add(authority)

        # RFC Forwarded header: Forwarded: for=...;proto=https;host=example.com
        forwarded = self.headers.get('Forwarded') or ''
        for part in forwarded.split(';'):
            key, sep, value = part.strip().partition('=')
            if sep and key.casefold() == 'host':
                authority = normalise_authority(value.strip('"'), parsed_origin.scheme)
                if authority:
                    allowed_authorities.add(authority)

        # Exact Quick Tunnel hostname recorded by the launcher.
        try:
            current_url = ROOT / '.align_beta' / 'CURRENT BETA URL.txt'
            if current_url.exists():
                public_url = current_url.read_text(encoding='utf-8-sig').strip()
                authority = normalise_authority(public_url)
                if authority:
                    allowed_authorities.add(authority)
        except Exception:
            pass

        if origin_authority and origin_authority in allowed_authorities:
            return True

        # Referer is a secondary compatibility fallback only when it agrees with
        # the browser Origin and the exact current public authority.
        referer = (self.headers.get('Referer') or '').strip()
        referer_authority = normalise_authority(referer)
        if origin_authority and referer_authority == origin_authority and origin_authority in allowed_authorities:
            return True

        self.send_json(403, {'error':'This beta request must come from the current Align site.'})
        return False

    def send_beta_cookie(self, token: str, clear: bool=False):
        value='' if clear else token
        age=0 if clear else 30*24*60*60
        forwarded=self.headers.get('X-Forwarded-Proto','').split(',')[0].strip().lower()
        is_https = forwarded == 'https' or isinstance(self.connection, ssl.SSLSocket)
        secure = '; Secure' if is_https else ''
        # Hosted tester access runs behind Cloudflare HTTPS. SameSite=None keeps the
        # session usable in Safari and embedded iPhone browsers opened from
        # another app; Secure is mandatory for None. Local HTTP diagnostics
        # deliberately stay Lax.
        same_site = 'None' if is_https else 'Lax'
        self.send_header('Set-Cookie',f'align_beta={value}; Path=/; Max-Age={age}; HttpOnly{secure}; SameSite={same_site}; Priority=High')

    def request_icloud_manager(self, row=None, restore=True):
        if BETA_MODE:
            row=row or self.beta_user()
            if not row: raise ValueError('Sign-in is required.')
            return beta_icloud_manager(row, restore)
        return icloud_manager()

    def beta_me_payload(self,row):
        return {'authenticated':bool(row),'build_version':BUILD_VERSION,'app_version':APP_VERSION,'terms_version':beta_store().terms_current(row) if row else False,
                'welcome_seen':bool(row and row['welcome_seen_at']),
                'user':({'user_id':row['user_id'],'email':row['email'],'display_name':row['display_name'],'is_owner':bool(row['is_owner']),'password_set':bool(row['password_hash'])} if row else None)}

    def rewrite_public_path(self):
        aliases = {
            '/login': '/beta-login', '/login.html': '/beta-login.html',
            '/invite': '/beta-invite', '/invite.html': '/beta-invite.html',
            '/forgot': '/beta-forgot', '/forgot.html': '/beta-forgot.html',
            '/reset': '/beta-reset', '/reset.html': '/beta-reset.html',
            '/terms': '/beta-terms', '/terms.html': '/beta-terms.html',
            '/welcome': '/beta-welcome', '/welcome.html': '/beta-welcome.html',
            '/account': '/beta-admin', '/account.html': '/beta-admin.html',
            '/login-submit': '/beta-login-submit',
            '/invite-complete': '/beta-invite-complete',
            '/reset-submit': '/beta-reset-submit',
        }
        parsed = urlparse(self.path)
        mapped = aliases.get(parsed.path)
        if mapped:
            self.path = mapped + (f'?{parsed.query}' if parsed.query else '')

    def do_GET(self):
        self.rewrite_public_path()
        if reject_retired_schedule_endpoint(self): return
        if build152.handle(self, sys.modules[__name__], 'GET'): return
        if phone_push.handle(self, sys.modules[__name__], 'GET'): return
        if asset_studio.handle(self, sys.modules[__name__], 'GET'): return
        if transport_service.handle(self, sys.modules[__name__], 'GET'): return
        if personal_planner.handle(self, sys.modules[__name__], 'GET'): return
        if owner_builder.handle(self, sys.modules[__name__], 'GET'): return
        parsed = urlparse(self.path)
        try:
            if health_backup.handle(self, sys.modules[__name__], "GET"):
                return
            if beta_http.handle_get(self, sys.modules[__name__], parsed):
                return
            if BETA_MODE and parsed.path.startswith('/api/'):
                row=self.require_beta_user()
                if not row: return
            else:
                row=self.beta_user() if BETA_MODE else None
            if icloud_api.handle_get(self, sys.modules[__name__], parsed, row):
                return
            with db_connection() as connection:
                if admin_api.handle(self, sys.modules[__name__], "GET", connection):
                    return
                if planner_api.handle_get(self, sys.modules[__name__], connection, parsed, row):
                    return
                if align_settings.handle(self, sys.modules[__name__], "GET", connection):
                    return

                if organiser_api.handle(self, sys.modules[__name__], "GET", connection):
                    return

        except BetaError as error:
            self.send_beta_error(error)
            return
        except (ValueError, sqlite3.Error) as error:
            self.send_json(400, {"error": str(error)})
            return
        beta_http.apply_pages(self, sys.modules[__name__], parsed)
        super().do_GET()

    def do_POST(self):
        self.rewrite_public_path()
        if reject_retired_schedule_endpoint(self): return
        if build152.handle(self, sys.modules[__name__], 'POST'): return
        if phone_push.handle(self, sys.modules[__name__], 'POST'): return
        if asset_studio.handle(self, sys.modules[__name__], 'POST'): return
        if transport_service.handle(self, sys.modules[__name__], 'POST'): return
        if personal_planner.handle(self, sys.modules[__name__], 'POST'): return
        if owner_builder.handle(self, sys.modules[__name__], 'POST'): return
        path = urlparse(self.path).path
        try:
            if beta_http.handle_form(self, sys.modules[__name__], path):
                return

            if health_backup.handle(self, sys.modules[__name__], "POST"):
                return

            payload = self.read_json()
            if beta_http.handle_post(self, sys.modules[__name__], path, payload):
                return
            if BETA_MODE and path.startswith('/api/'):
                row=self.require_beta_user()
                if not row: return
                if not self.beta_same_origin(): return
            else: row=self.beta_user() if BETA_MODE else None
            if icloud_api.handle_post(self, sys.modules[__name__], path, row, payload):
                return
            if admin_api.handle(self, sys.modules[__name__], "POST", payload=payload):
                return
            with db_connection() as connection:
                if organiser_api.handle(self, sys.modules[__name__], "POST", connection, payload, row):
                    return
                if admin_api.handle(self, sys.modules[__name__], "POST", connection, payload):
                    return
                if planner_api.handle_post(self, sys.modules[__name__], connection, path, payload, row):
                    return
        except BetaError as error:
            self.send_beta_error(error)
            return
        except (KeyError, ValueError, sqlite3.IntegrityError, sqlite3.Error) as error:
            self.send_json(400, {"error": str(error)})
            return
        self.send_json(404, {"error": "Not found"})

    def do_PUT(self):
        if reject_retired_schedule_endpoint(self): return
        if build152.handle(self, sys.modules[__name__], 'PUT'): return
        if personal_planner.handle(self, sys.modules[__name__], 'PUT'): return
        if owner_builder.handle(self, sys.modules[__name__], 'PUT'): return
        path = urlparse(self.path).path
        try:
            payload = self.read_json()
            if beta_http.handle_put(self, sys.modules[__name__], path, payload):
                return
            row=self.require_beta_user() if BETA_MODE else None
            if BETA_MODE and not row: return
            if BETA_MODE and not self.beta_same_origin(): return
            with db_connection() as connection:
                if organiser_api.handle(self, sys.modules[__name__], "PUT", connection, payload, row):
                    return
                if align_settings.handle(self, sys.modules[__name__], "PUT", connection, payload):
                    return
                if planner_api.handle_put(self, sys.modules[__name__], connection, path, payload, row):
                    return
                if admin_api.handle(self, sys.modules[__name__], "PUT", connection, payload):
                    return

        except BetaError as error:
            self.send_beta_error(error)
            return
        except (KeyError, TypeError, ValueError, sqlite3.IntegrityError, sqlite3.Error) as error:
            self.send_json(400, {"error": str(error)})
            return
        self.send_json(404, {"error": "Not found"})

    def do_DELETE(self):
        if reject_retired_schedule_endpoint(self): return
        if personal_planner.handle(self, sys.modules[__name__], 'DELETE'): return
        if owner_builder.handle(self, sys.modules[__name__], 'DELETE'): return
        path = urlparse(self.path).path
        try:
            if beta_http.handle_delete(self, sys.modules[__name__], path):
                return
            row=self.require_beta_user() if BETA_MODE else None
            if BETA_MODE and not row: return
            if BETA_MODE and not self.beta_same_origin(): return
            with db_connection() as connection:
                if organiser_api.handle(self, sys.modules[__name__], "DELETE", connection, row=row):
                    return
                if planner_api.handle_delete(self, sys.modules[__name__], connection, path, row):
                    return
        except (ValueError, sqlite3.Error) as error:
            self.send_json(400, {"error": str(error)})
            return
        self.send_json(404, {"error": "Not found"})


class AlignServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        if os.name == 'nt' and hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    network_mode = "--network" in sys.argv
    beta_mode = BETA_MODE
    host = "127.0.0.1" if beta_mode else ("0.0.0.0" if network_mode else "127.0.0.1")
    port = int(os.environ.get("ALIGN_PORT", "8010" if beta_mode else "8001"))
    admin_port = int(os.environ.get("ALIGN_ADMIN_PORT", "8003"))
    if network_mode and not beta_mode and not ADMIN_PASSWORD:
        sys.exit('Set ALIGN_ADMIN_PASSWORD before starting network mode. See the install guide.')

    try:
        server = AlignServer((host, port), AlignHandler)
    except OSError:
        sys.exit(f'Port {port} is unavailable. Close the existing Align server before starting another copy.')

    admin_server = None
    if network_mode and not beta_mode:
        try:
            # PC-only HTTP listener. Binding to loopback means phones/other LAN devices
            # cannot reach iCloud credential management, and Windows does not need to
            # trust Align's private HTTPS CA merely to open Admin.
            admin_server = AlignServer(("127.0.0.1", admin_port), AlignHandler)
        except OSError:
            server.server_close()
            sys.exit(f'Admin port {admin_port} is unavailable. Close anything using it, then restart Align.')

    initialise_database()
    scheme = "http"
    certfile = os.environ.get("ALIGN_SSL_CERT")
    keyfile = os.environ.get("ALIGN_SSL_KEY")
    if certfile or keyfile:
        if not certfile or not keyfile:
            if admin_server:
                admin_server.server_close()
            server.server_close()
            sys.exit('Both ALIGN_SSL_CERT and ALIGN_SSL_KEY are required for HTTPS mode.')
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(certfile=certfile, keyfile=keyfile)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        scheme = "https"

    admin_thread = None
    if admin_server is not None:
        admin_thread = threading.Thread(target=admin_server.serve_forever, name="AlignLocalAdmin", daemon=True)
        admin_thread.start()
        print(f"PC Admin is ready at http://127.0.0.1:{admin_port}/admin")

    if beta_mode:
        beta_store()
        restore_all_beta_icloud()
        print(f"Align V3.0 is ready locally at {scheme}://{host}:{port}")
    else:
        print(f"Align V3.0 is ready at {scheme}://{host}:{port}")
    LOG.info("Align server started mode=%s port=%s", "beta" if beta_mode else "normal", port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nAlign stopped. Your saved data is kept in align.sqlite3.')
    finally:
        LOG.info("Align server stopping")
        server.server_close()
        if admin_server is not None:
            admin_server.shutdown()
            admin_server.server_close()
