"""Local desktop account and persistent-session storage for Align.

Only salted password hashes and hashed random session tokens are stored. The
browser receives an HttpOnly cookie; no password or bearer token is written to
localStorage or the planner database.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import time
from pathlib import Path

from desktop.paths import user_data_dir

DB_NAME = "desktop-auth.sqlite3"
PBKDF2_ROUNDS = 600_000
REMEMBER_SECONDS = 30 * 24 * 60 * 60
SESSION_SECONDS = 12 * 60 * 60


class DesktopAuthError(ValueError):
    pass


class _ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class DesktopAuthStore:
    def __init__(self, database: Path | str | None = None) -> None:
        self.database = Path(database) if database else user_data_dir() / DB_NAME
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=10, factory=_ClosingConnection)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def _initialise(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS desktop_owner (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    email TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    password_salt TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS desktop_sessions (
                    token_hash TEXT PRIMARY KEY,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_desktop_sessions_expiry
                    ON desktop_sessions(expires_at);
            """)

    @staticmethod
    def _normalise_email(email: str) -> str:
        value = str(email or "").strip().casefold()
        if len(value) > 254 or value.count("@") != 1:
            raise DesktopAuthError("Enter a valid email address.")
        local, domain = value.split("@", 1)
        if not local or not domain or "." not in domain or any(ch.isspace() for ch in value):
            raise DesktopAuthError("Enter a valid email address.")
        return value

    @staticmethod
    def _password_hash(password: str, salt: bytes) -> bytes:
        return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("ascii")).hexdigest()

    @staticmethod
    def _public_user(row: sqlite3.Row) -> dict:
        return {"email": row["email"], "display_name": row["display_name"], "role": "Owner"}

    def has_account(self) -> bool:
        with self._connect() as connection:
            return connection.execute("SELECT 1 FROM desktop_owner WHERE id=1").fetchone() is not None

    def _create_session(self, connection: sqlite3.Connection, remember: bool, now: int) -> tuple[str, int]:
        token = secrets.token_urlsafe(40)
        expires_at = now + (REMEMBER_SECONDS if remember else SESSION_SECONDS)
        connection.execute(
            "INSERT INTO desktop_sessions(token_hash,created_at,expires_at) VALUES(?,?,?)",
            (self._token_hash(token), now, expires_at),
        )
        return token, expires_at

    def setup(self, email: str, display_name: str, password: str, remember: bool = True, now: int | None = None) -> tuple[str, dict, int]:
        email = self._normalise_email(email)
        display_name = str(display_name or "").strip()[:80]
        password = str(password or "")
        if not display_name:
            raise DesktopAuthError("Enter your name.")
        if len(password) < 12:
            raise DesktopAuthError("Use a password with at least 12 characters.")
        if len(password) > 1024:
            raise DesktopAuthError("That password is too long.")
        timestamp = int(time.time() if now is None else now)
        salt = secrets.token_bytes(32)
        digest = self._password_hash(password, salt)
        with self._connect() as connection:
            if connection.execute("SELECT 1 FROM desktop_owner WHERE id=1").fetchone():
                raise DesktopAuthError("The local Owner account has already been created. Sign in instead.")
            connection.execute(
                "INSERT INTO desktop_owner(id,email,display_name,password_salt,password_hash,created_at) VALUES(1,?,?,?,?,?)",
                (email, display_name, salt.hex(), digest.hex(), timestamp),
            )
            token, expires_at = self._create_session(connection, bool(remember), timestamp)
            row = connection.execute("SELECT * FROM desktop_owner WHERE id=1").fetchone()
        return token, self._public_user(row), expires_at

    def authenticate(self, email: str, password: str, remember: bool = True, now: int | None = None) -> tuple[str, dict, int] | None:
        try:
            email = self._normalise_email(email)
        except DesktopAuthError:
            return None
        password = str(password or "")
        if not password or len(password) > 1024:
            return None
        timestamp = int(time.time() if now is None else now)
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM desktop_owner WHERE id=1 AND email=?", (email,)).fetchone()
            if row is None:
                return None
            try:
                salt = bytes.fromhex(row["password_salt"])
                expected = bytes.fromhex(row["password_hash"])
            except ValueError:
                return None
            actual = self._password_hash(password, salt)
            if not hmac.compare_digest(actual, expected):
                return None
            token, expires_at = self._create_session(connection, bool(remember), timestamp)
        return token, self._public_user(row), expires_at

    def get_session(self, token: str, now: int | None = None) -> dict | None:
        if not token or len(token) > 256:
            return None
        timestamp = int(time.time() if now is None else now)
        digest = self._token_hash(token)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT s.expires_at,o.email,o.display_name FROM desktop_sessions s "
                "JOIN desktop_owner o ON o.id=1 WHERE s.token_hash=?",
                (digest,),
            ).fetchone()
            if row is None:
                return None
            if int(row["expires_at"]) <= timestamp:
                connection.execute("DELETE FROM desktop_sessions WHERE token_hash=?", (digest,))
                return None
            return {"email": row["email"], "display_name": row["display_name"], "role": "Owner", "expires_at": int(row["expires_at"])}

    def revoke(self, token: str) -> None:
        if not token:
            return
        with self._connect() as connection:
            connection.execute("DELETE FROM desktop_sessions WHERE token_hash=?", (self._token_hash(token),))

    def revoke_all(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM desktop_sessions")
