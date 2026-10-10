"""Build 152 additions: persistent user favourites.

This module deliberately owns its small feature surface so the main handler remains
stable. Favourites are stored in the user's active Align database and are safe to
use in both normal and beta modes.
"""
from __future__ import annotations
import json
import re
import sqlite3
from datetime import datetime, timezone

ENTITY_TYPES = {"location", "event_title", "event_location", "section"}
CONTACT_MAX_NAME = 160
CONTACT_MAX_ADDRESS = 500
CONTACT_MAX_PHONE = 80
CONTACT_SCHEMA = """CREATE TABLE IF NOT EXISTS align_contacts (id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,address TEXT NOT NULL DEFAULT '',phone TEXT NOT NULL DEFAULT '',notes TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(name,address,phone))"""
MAX_LABEL = 160
MAX_VALUE = 1000

def ensure(connection):
    connection.execute("""
        CREATE TABLE IF NOT EXISTS user_favourites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            entity_key TEXT NOT NULL,
            label TEXT NOT NULL,
            value TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(entity_type, entity_key)
        )
    """)
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_favourites_type_updated "
        "ON user_favourites(entity_type, updated_at DESC)"
    )

def _clean(value, limit):
    return str(value or "").strip()[:limit]

def _payload(raw):
    try:
        value = json.loads(raw or b"{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        raise ValueError("Send a valid JSON object.")
    if not isinstance(value, dict):
        raise ValueError("Send a JSON object.")

    entity_type = _clean(value.get("entity_type"), 40)
    entity_key = _clean(value.get("entity_key"), 240)
    label = _clean(value.get("label"), MAX_LABEL)
    stored = value.get("value", "")
    if isinstance(stored, (dict, list)):
        stored = json.dumps(stored, ensure_ascii=False)
    stored = _clean(stored, MAX_VALUE)
    if entity_type not in ENTITY_TYPES:
        raise ValueError("Unknown favourite type.")
    if not entity_key or not label:
        raise ValueError("A favourite needs a label and key.")
    metadata = value.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    metadata = json.dumps(metadata, ensure_ascii=False)[:4000]
    return entity_type, entity_key, label, stored, metadata, bool(value.get("active", True))

def _rows(connection):
    return [dict(row) for row in connection.execute(
        """SELECT id, entity_type, entity_key, label, value, metadata_json,
                  created_at, updated_at
           FROM user_favourites
           ORDER BY entity_type, updated_at DESC, id DESC"""
    ).fetchall()]

def _contact_payload(raw):
    try:
        value = json.loads(raw or b"{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        raise ValueError("Send a valid JSON object.")
    if not isinstance(value, dict):
        raise ValueError("Send a JSON object.")
    name = _clean(value.get("name"), CONTACT_MAX_NAME)
    address = _clean(value.get("address"), CONTACT_MAX_ADDRESS)
    phone = _clean(value.get("phone"), CONTACT_MAX_PHONE)
    notes = _clean(value.get("notes"), 1000)
    if not name:
        raise ValueError("A contact needs a name.")
    return name, address, phone, notes

def _contact_rows(connection):
    return [dict(row) for row in connection.execute(
        "SELECT id, name, address, phone, notes, created_at, updated_at FROM align_contacts ORDER BY name COLLATE NOCASE, id"
    ).fetchall()]

def _contact_from_id(connection, contact_id):
    row = connection.execute("SELECT id, name, address, phone, notes FROM align_contacts WHERE id=?", (int(contact_id),)).fetchone()
    return dict(row) if row else None

def _save_contact(connection, values):
    name, address, phone, notes = values
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    connection.execute(
        "INSERT INTO align_contacts (name,address,phone,notes,created_at,updated_at) VALUES (?,?,?,?,?,?) "
        "ON CONFLICT(name,address,phone) DO UPDATE SET notes=excluded.notes, updated_at=excluded.updated_at",
        (name, address, phone, notes, now, now),
    )
    row = connection.execute(
        "SELECT id,name,address,phone,notes,created_at,updated_at FROM align_contacts WHERE name=? AND address=? AND phone=?",
        (name, address, phone),
    ).fetchone()
    return dict(row) if row else None

def _update_contact(connection, contact_id, values):
    name, address, phone, notes = values
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cursor = connection.execute(
        "UPDATE align_contacts SET name=?,address=?,phone=?,notes=?,updated_at=? WHERE id=?",
        (name, address, phone, notes, now, int(contact_id)),
    )
    if cursor.rowcount != 1:
        return None
    return dict(connection.execute(
        "SELECT id,name,address,phone,notes,created_at,updated_at FROM align_contacts WHERE id=?",
        (int(contact_id),),
    ).fetchone())

def handle(handler, app, method):
    path = handler.path.split("?", 1)[0]
    contact_match = re.fullmatch(r"/api/contacts/(\d+)", path)
    if path == "/api/contacts" or contact_match:
        if app.BETA_MODE and not handler.require_beta_user():
            return True
        if app.BETA_MODE and method in {"POST", "PUT"} and not handler.beta_same_origin():
            return True
        if path == "/api/contacts" and method == "GET":
            with app.db_connection() as connection:
                connection.execute(CONTACT_SCHEMA)
                rows = _contact_rows(connection)
            handler.send_json(200, {"contacts": rows, "build": app.BUILD_VERSION})
            return True
        if path == "/api/contacts" and method == "POST":
            length = int(handler.headers.get("Content-Length", "0") or "0")
            if length < 0 or length > 32_000:
                handler.send_json(413, {"error": "Contact request is too large."})
                return True
            values = _contact_payload(handler.rfile.read(length))
            with app.db_connection() as connection:
                connection.execute(CONTACT_SCHEMA)
                row = _save_contact(connection, values)
                connection.commit()
            handler.send_json(200, {"contact": row, "saved": bool(row)})
            return True
        if contact_match and method == "PUT":
            length = int(handler.headers.get("Content-Length", "0") or "0")
            if length < 0 or length > 32_000:
                handler.send_json(413, {"error": "Contact request is too large."})
                return True
            values = _contact_payload(handler.rfile.read(length))
            with app.db_connection() as connection:
                connection.execute(CONTACT_SCHEMA)
                try:
                    row = _update_contact(connection, int(contact_match.group(1)), values)
                except sqlite3.IntegrityError:
                    handler.send_json(409, {"error": "A saved contact with those details already exists."})
                    return True
                connection.commit()
            if not row:
                handler.send_json(404, {"error": "Contact not found."})
                return True
            handler.send_json(200, {"contact": row, "saved": True})
            return True
        if contact_match or method != "GET":
            handler.send_json(405, {"error": "Method not allowed"})
            return True

    if path != "/api/favourites":
        return False

    if app.BETA_MODE and not handler.require_beta_user():
        return True

    if method == "GET":
        with app.db_connection() as connection:
            ensure(connection)
            rows = _rows(connection)
        for row in rows:
            try:
                row["metadata"] = json.loads(row.pop("metadata_json") or "{}")
            except (TypeError, ValueError):
                row["metadata"] = {}
        handler.send_json(200, {"favourites": rows, "build": app.BUILD_VERSION})
        return True

    if method != "POST":
        handler.send_json(405, {"error": "Method not allowed"})
        return True

    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length < 0 or length > 32_000:
        handler.send_json(413, {"error": "Favourite request is too large."})
        return True

    raw = handler.rfile.read(length)
    entity_type, entity_key, label, value, metadata, active = _payload(raw)

    with app.db_connection() as connection:
        ensure(connection)
        if active:
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            connection.execute(
                """INSERT INTO user_favourites
                   (entity_type, entity_key, label, value, metadata_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(entity_type, entity_key) DO UPDATE SET
                     label=excluded.label,
                     value=excluded.value,
                     metadata_json=excluded.metadata_json,
                     updated_at=excluded.updated_at""",
                (entity_type, entity_key, label, value, metadata, now, now),
            )
        else:
            connection.execute(
                "DELETE FROM user_favourites WHERE entity_type=? AND entity_key=?",
                (entity_type, entity_key),
            )
        connection.commit()
        row = connection.execute(
            """SELECT id, entity_type, entity_key, label, value, metadata_json,
                      created_at, updated_at
               FROM user_favourites
               WHERE entity_type=? AND entity_key=?""",
            (entity_type, entity_key),
        ).fetchone()

    result = dict(row) if row else None
    if result:
        try:
            result["metadata"] = json.loads(result.pop("metadata_json") or "{}")
        except (TypeError, ValueError):
            result["metadata"] = {}
    handler.send_json(200, {"saved": bool(result), "favourite": result})
    return True
