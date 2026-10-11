"""Account, invite, recovery and private-data support for Align V3.0.

The registry is intentionally separate from every planner database. Owner tools can
manage access, the shared default structure and deliberately submitted feedback,
but have no API for browsing tester planner content.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import sqlite3
from sqlite_support import connect, postgres_enabled
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

TERMS_VERSION = "2026-09-03"
PRIVACY_VERSION = "2026-09-03"
SESSION_SECONDS = 30 * 24 * 60 * 60
INVITE_SECONDS = 7 * 24 * 60 * 60
RESET_SECONDS = 30 * 60
IDEMPOTENCY_SECONDS = 24 * 60 * 60
PASSWORD_MIN = 10
PASSWORD_MAX = 128


class BetaError(ValueError):
    def __init__(self, message: str, code: str = "invalid_request", status: int = 400, retry_after: int | None = None):
        super().__init__(message)
        self.code = code
        self.status = status
        self.retry_after = retry_after


class BetaStore:
    def __init__(self, root: Path, owner_database: Path, initialise_database_at):
        self.root = Path(root)
        self.owner_database = Path(owner_database)
        self.registry = self.root / "beta_users.sqlite3"
        self.data_dir = self.root / "beta_data"
        self.secret_file = self.root / "beta_secret.key"
        self.rsa_private_file = self.root / "beta_credential_private.pem"
        self.initialise_database_at = initialise_database_at
        self.lock = threading.RLock()
        self.login_lock = threading.Lock()
        self.login_attempts: dict[str, list[float]] = {}
        self.reset_attempts: dict[str, list[float]] = {}
        self.idempotency_memory: dict[str, tuple[float, str, dict, int]] = {}
        self.data_dir.mkdir(exist_ok=True)
        self._init_registry()

    def _connect(self):
        con = connect(self.registry)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=5000")
        return con

    def _init_registry(self):
        if postgres_enabled():
            from postgres_support import validate_auth
            with self._connect() as c:
                validate_auth(c)
            return
        with self._connect() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS beta_users (
              user_id TEXT PRIMARY KEY,
              email TEXT NOT NULL UNIQUE COLLATE NOCASE,
              invite_hash TEXT NOT NULL,
              session_hash TEXT NOT NULL DEFAULT '',
              session_expires INTEGER NOT NULL DEFAULT 0,
              database_path TEXT NOT NULL,
              is_owner INTEGER NOT NULL DEFAULT 0 CHECK(is_owner IN(0,1)),
              active INTEGER NOT NULL DEFAULT 1 CHECK(active IN(0,1)),
              terms_version TEXT NOT NULL DEFAULT '',
              privacy_version TEXT NOT NULL DEFAULT '',
              accepted_at TEXT NOT NULL DEFAULT '',
              welcome_seen_at TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              last_login TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS beta_sessions (
              session_hash TEXT PRIMARY KEY,
              user_id TEXT NOT NULL REFERENCES beta_users(user_id) ON DELETE CASCADE,
              expires INTEGER NOT NULL,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              last_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_beta_sessions_user ON beta_sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_beta_sessions_expires ON beta_sessions(expires);
            CREATE TABLE IF NOT EXISTS beta_icloud_credentials (
              user_id TEXT PRIMARY KEY REFERENCES beta_users(user_id) ON DELETE CASCADE,
              username_enc TEXT NOT NULL,
              password_enc TEXT NOT NULL,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS beta_feedback (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id TEXT NOT NULL REFERENCES beta_users(user_id) ON DELETE CASCADE,
              feedback_type TEXT NOT NULL,
              message TEXT NOT NULL,
              build_version INTEGER NOT NULL,
              screen TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """)
            cols = {r[1] for r in c.execute("PRAGMA table_info(beta_users)")}
            migrations = {
                'session_expires': "ALTER TABLE beta_users ADD COLUMN session_expires INTEGER NOT NULL DEFAULT 0",
                'welcome_seen_at': "ALTER TABLE beta_users ADD COLUMN welcome_seen_at TEXT NOT NULL DEFAULT ''",
                'display_name': "ALTER TABLE beta_users ADD COLUMN display_name TEXT NOT NULL DEFAULT ''",
                'password_hash': "ALTER TABLE beta_users ADD COLUMN password_hash TEXT NOT NULL DEFAULT ''",
                'password_set_at': "ALTER TABLE beta_users ADD COLUMN password_set_at TEXT NOT NULL DEFAULT ''",
                'account_status': "ALTER TABLE beta_users ADD COLUMN account_status TEXT NOT NULL DEFAULT 'active'",
            }
            for col, sql in migrations.items():
                if col not in cols:
                    c.execute(sql)
            # Existing Build 137-140 users are established accounts. Newly-created
            # V3.0 testers are explicitly marked pending until invite completion.
            c.execute("UPDATE beta_users SET account_status='active' WHERE account_status='' OR account_status IS NULL")
            c.executescript("""
            CREATE TABLE IF NOT EXISTS beta_invites (
              invite_id TEXT PRIMARY KEY,
              user_id TEXT NOT NULL REFERENCES beta_users(user_id) ON DELETE CASCADE,
              code_hash TEXT NOT NULL UNIQUE,
              status TEXT NOT NULL CHECK(status IN('pending','used','expired','revoked','replaced')),
              created_at INTEGER NOT NULL,
              expires_at INTEGER NOT NULL,
              used_at INTEGER,
              revoked_at INTEGER,
              replaced_at INTEGER,
              replaced_by_invite_id TEXT,
              delivery_status TEXT NOT NULL DEFAULT 'not_attempted'
                CHECK(delivery_status IN('not_attempted','sending','retry_wait','sent','failed','not_confirmed')),
              delivery_attempts INTEGER NOT NULL DEFAULT 0,
              last_delivery_at INTEGER,
              last_delivery_error TEXT NOT NULL DEFAULT '',
              created_by_user_id TEXT,
              FOREIGN KEY(replaced_by_invite_id) REFERENCES beta_invites(invite_id)
            );
            CREATE INDEX IF NOT EXISTS idx_beta_invites_user ON beta_invites(user_id,created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_beta_invites_expiry ON beta_invites(expires_at);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_beta_one_pending_invite
              ON beta_invites(user_id) WHERE status='pending';

            CREATE TABLE IF NOT EXISTS beta_password_resets (
              reset_id TEXT PRIMARY KEY,
              user_id TEXT NOT NULL REFERENCES beta_users(user_id) ON DELETE CASCADE,
              code_hash TEXT NOT NULL UNIQUE,
              status TEXT NOT NULL CHECK(status IN('pending','used','expired','revoked','replaced')),
              created_at INTEGER NOT NULL,
              expires_at INTEGER NOT NULL,
              used_at INTEGER,
              revoked_at INTEGER,
              replaced_at INTEGER,
              replaced_by_reset_id TEXT,
              delivery_status TEXT NOT NULL DEFAULT 'not_attempted',
              delivery_attempts INTEGER NOT NULL DEFAULT 0,
              last_delivery_at INTEGER,
              last_delivery_error TEXT NOT NULL DEFAULT '',
              FOREIGN KEY(replaced_by_reset_id) REFERENCES beta_password_resets(reset_id)
            );
            CREATE INDEX IF NOT EXISTS idx_beta_reset_user ON beta_password_resets(user_id,created_at DESC);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_beta_one_pending_reset
              ON beta_password_resets(user_id) WHERE status='pending';

            CREATE TABLE IF NOT EXISTS beta_idempotency (
              key_hash TEXT PRIMARY KEY,
              owner_user_id TEXT NOT NULL,
              operation TEXT NOT NULL,
              request_hash TEXT NOT NULL,
              result_id TEXT NOT NULL DEFAULT '',
              http_status INTEGER NOT NULL,
              response_json TEXT NOT NULL DEFAULT '{}',
              created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_beta_idempotency_created ON beta_idempotency(created_at);

            CREATE TABLE IF NOT EXISTS beta_rate_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              bucket TEXT NOT NULL,
              subject_hash TEXT NOT NULL,
              created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_beta_rate_events_lookup
              ON beta_rate_events(bucket,subject_hash,created_at);

            CREATE TABLE IF NOT EXISTS beta_audit_events (
              event_id TEXT PRIMARY KEY,
              event_type TEXT NOT NULL,
              user_id TEXT,
              invite_id TEXT,
              reset_id TEXT,
              outcome TEXT NOT NULL,
              reason TEXT NOT NULL DEFAULT '',
              request_id TEXT NOT NULL DEFAULT '',
              details_json TEXT NOT NULL DEFAULT '{}',
              created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_beta_audit_created ON beta_audit_events(created_at DESC);

            CREATE TABLE IF NOT EXISTS beta_email_settings (
              singleton INTEGER PRIMARY KEY CHECK(singleton=1),
              sender_email TEXT NOT NULL DEFAULT '',
              sender_name TEXT NOT NULL DEFAULT 'Align',
              smtp_host TEXT NOT NULL DEFAULT 'smtp-mail.outlook.com',
              smtp_port INTEGER NOT NULL DEFAULT 587,
              encryption TEXT NOT NULL DEFAULT 'starttls',
              oauth_client_id TEXT NOT NULL DEFAULT '',
              oauth_authority TEXT NOT NULL DEFAULT 'consumers',
              oauth_cache_enc TEXT NOT NULL DEFAULT '',
              connection_status TEXT NOT NULL DEFAULT 'not_configured',
              last_checked_at TEXT NOT NULL DEFAULT '',
              last_success_at TEXT NOT NULL DEFAULT '',
              last_error TEXT NOT NULL DEFAULT '',
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT OR IGNORE INTO beta_email_settings(singleton) VALUES(1);
            """)

    @staticmethod
    def digest(value: str) -> str:
        return hashlib.sha256(value.encode('utf-8')).hexdigest()

    @staticmethod
    def canonical_code(value: str) -> str:
        return str(value or '').strip().upper()

    @staticmethod
    def new_code(prefix: str = 'ALIGN') -> str:
        # 48 random bits encoded as 12 hexadecimal characters, grouped for readability.
        raw = secrets.token_hex(6).upper()
        return prefix + '-' + '-'.join(raw[i:i+4] for i in range(0, 12, 4))

    @staticmethod
    def now() -> int:
        return int(time.time())

    @staticmethod
    def iso(epoch: int | None) -> str:
        if not epoch:
            return ''
        return datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace('+00:00','Z')

    @staticmethod
    def validate_password(password: str) -> None:
        value = str(password or '')
        if len(value) < PASSWORD_MIN or len(value) > PASSWORD_MAX:
            raise BetaError(f'Password must be {PASSWORD_MIN}–{PASSWORD_MAX} characters.', 'invalid_password')
        if any(ch.isspace() for ch in value):
            raise BetaError('Password must not contain spaces.', 'invalid_password')
        if not re.search(r'[A-Za-z]', value):
            raise BetaError('Password must contain at least one letter.', 'invalid_password')
        if not re.search(r'[0-9]', value):
            raise BetaError('Password must contain at least one number.', 'invalid_password')

    @staticmethod
    def _password_hasher():
        try:
            from argon2 import PasswordHasher
            from argon2.low_level import Type
        except ImportError:
            raise BetaError('Run Install Align Add-ons.bat and choose Owner accounts and remote access to install secure password support.', 'beta_support_missing', 503) from None
        return PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2, hash_len=32, salt_len=16, type=Type.ID)

    def hash_password(self, password: str) -> str:
        self.validate_password(password)
        return self._password_hasher().hash(password)

    def verify_password(self, stored: str, password: str) -> bool:
        if not stored:
            return False
        try:
            from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
            return bool(self._password_hasher().verify(stored, str(password or '')))
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def owner(self):
        with self._connect() as c:
            return c.execute("SELECT * FROM beta_users WHERE is_owner=1 LIMIT 1").fetchone()

    def ensure_owner(self, email: str):
        email = email.strip().casefold()
        if '@' not in email:
            raise BetaError('Enter a valid owner email address.')
        current = self.owner()
        if current:
            return dict(current), None
        code = self.new_code('OWNER')
        uid = secrets.token_hex(12)
        self.initialise_database_at(self.owner_database)
        with self._connect() as c:
            c.execute("""INSERT INTO beta_users(user_id,email,invite_hash,database_path,is_owner,account_status)
                         VALUES(?,?,?,?,1,'active')""",
                      (uid,email,self.digest(self.canonical_code(code)),self.owner_database.name))
        return dict(self.owner()), code

    def database_for(self, row) -> Path:
        if postgres_enabled():
            if row['is_owner']:
                return self.owner_database
            value = Path(row['database_path'])
            user_id = row.get('user_id') if hasattr(row, 'get') else row['user_id'] if 'user_id' in row.keys() else None
            if not user_id or value.parent.name != 'beta_data' or value.name != f"{user_id}.sqlite3":
                raise BetaError('Invalid hosted tester database path.', 'hosted_storage_unavailable', 503)
            return self.root / value
        value = Path(row['database_path'])
        if value.name == self.owner_database.name and row['is_owner']:
            return self.owner_database
        path = (self.root / value).resolve()
        allowed = self.data_dir.resolve()
        if allowed not in path.parents:
            raise BetaError('Invalid beta database path.')
        return path

    def terms_current(self,row) -> bool:
        return bool(row and row['terms_version'] == TERMS_VERSION and row['privacy_version'] == PRIVACY_VERSION)

    def by_session(self, token: str):
        if not token:
            return None
        now = self.now()
        digest = self.digest(token)
        with self._connect() as c:
            c.execute("DELETE FROM beta_sessions WHERE expires<=?", (now,))
            row = c.execute("""SELECT u.* FROM beta_sessions s
                             JOIN beta_users u ON u.user_id=s.user_id
                             WHERE s.session_hash=? AND s.expires>? AND u.active=1 AND u.account_status='active'""",
                          (digest,now)).fetchone()
            if row:
                c.execute("UPDATE beta_sessions SET last_seen=CURRENT_TIMESTAMP WHERE session_hash=?", (digest,))
                return row
            # Compatibility with sessions issued before Build 138.
            row = c.execute("SELECT * FROM beta_users WHERE session_hash=? AND active=1 AND account_status='active' AND session_expires>?",
                          (digest,now)).fetchone()
            if row:
                c.execute("INSERT OR REPLACE INTO beta_sessions(session_hash,user_id,expires) VALUES(?,?,?)",
                          (digest,row['user_id'],int(row['session_expires'])))
            return row

    def _attempt_key(self, email, remote):
        return f"{remote}|{str(email or '').strip().casefold()}"

    @staticmethod
    def _delay_for_failures(count: int) -> int:
        if count < 5: return 0
        if count == 5: return 30
        if count == 6: return 60
        if count == 7: return 120
        return 300

    def _attempt_check(self, storage: dict[str,list[float]], key: str) -> None:
        now = time.monotonic(); cutoff = now - 3600
        with self.login_lock:
            values = [x for x in storage.get(key, []) if x >= cutoff]
            storage[key] = values
            if values:
                delay = self._delay_for_failures(len(values))
                if delay and now - values[-1] < delay:
                    retry = max(1, int(delay - (now-values[-1])))
                    raise BetaError('Too many unsuccessful attempts. Please wait before trying again.', 'too_many_requests', 429, retry)

    def _attempt_fail(self, storage: dict[str,list[float]], key: str):
        with self.login_lock:
            storage.setdefault(key, []).append(time.monotonic())

    def _attempt_success(self, storage: dict[str,list[float]], key: str):
        with self.login_lock:
            storage.pop(key, None)

    def _new_session(self, c: sqlite3.Connection, row) -> str:
        token = secrets.token_urlsafe(40)
        expires = self.now() + SESSION_SECONDS
        digest = self.digest(token)
        c.execute("UPDATE beta_users SET session_hash=?,session_expires=?,last_login=CURRENT_TIMESTAMP WHERE user_id=?",
                  (digest,expires,row['user_id']))
        c.execute("INSERT INTO beta_sessions(session_hash,user_id,expires) VALUES(?,?,?)",
                  (digest,row['user_id'],expires))
        return token

    def login(self, email, credential, remote=''):
        """Password login, with a compatibility path for the pre-V3.0 Owner code."""
        email = str(email or '').strip().casefold()
        credential = str(credential or '')
        key = self._attempt_key(email, remote)
        self._attempt_check(self.login_attempts, key)
        with self._connect() as c:
            row = c.execute("SELECT * FROM beta_users WHERE email=? AND active=1 AND account_status='active'", (email,)).fetchone()
            ok = False
            legacy_owner = False
            if row:
                if row['password_hash']:
                    ok = self.verify_password(row['password_hash'], credential)
                elif row['is_owner']:
                    legacy_owner = secrets.compare_digest(row['invite_hash'], self.digest(self.canonical_code(credential)))
                    ok = legacy_owner
            if not ok:
                self._attempt_fail(self.login_attempts, key)
                return None, None
            token = self._new_session(c, row)
        self._attempt_success(self.login_attempts, key)
        return self.by_session(token), token

    def logout(self,row, token: str=''):
        if not row: return
        digest = self.digest(token) if token else ''
        with self._connect() as c:
            if digest:
                c.execute("DELETE FROM beta_sessions WHERE session_hash=? AND user_id=?", (digest,row['user_id']))
            else:
                c.execute("DELETE FROM beta_sessions WHERE user_id=?", (row['user_id'],))
            if digest and row['session_hash'] == digest:
                c.execute("UPDATE beta_users SET session_hash='',session_expires=0 WHERE user_id=?", (row['user_id'],))

    def revoke_sessions(self, user_id: str) -> int:
        with self._connect() as c:
            count = c.execute("SELECT COUNT(*) FROM beta_sessions WHERE user_id=?", (user_id,)).fetchone()[0]
            c.execute("DELETE FROM beta_sessions WHERE user_id=?", (user_id,))
            c.execute("UPDATE beta_users SET session_hash='',session_expires=0 WHERE user_id=?", (user_id,))
            return int(count)

    def change_owner_email(self, row, current_password, new_email):
        new_email = str(new_email or '').strip().casefold()
        if '@' not in new_email:
            raise BetaError('Enter a valid Align login email address.', 'invalid_email')
        if not self.verify_password(row['password_hash'], str(current_password or '')):
            raise BetaError('Current Align password is incorrect.', 'invalid_credentials', 401)
        with self._connect() as c:
            exists = c.execute('SELECT user_id FROM beta_users WHERE email=? AND user_id<>?', (new_email,row['user_id'])).fetchone()
            if exists: raise BetaError('That email is already in use.', 'email_in_use', 409)
            c.execute('UPDATE beta_users SET email=? WHERE user_id=?', (new_email,row['user_id']))
        self.revoke_sessions(row['user_id'])
        return {'updated': True, 'email': new_email, 'signed_out': True}

    def accept_terms(self,row):
        with self._connect() as c:
            c.execute("UPDATE beta_users SET terms_version=?,privacy_version=?,accepted_at=CURRENT_TIMESTAMP WHERE user_id=?",
                      (TERMS_VERSION,PRIVACY_VERSION,row['user_id']))
        return self.user(row['user_id'])

    def mark_welcome(self,row):
        with self._connect() as c:
            c.execute("UPDATE beta_users SET welcome_seen_at=CURRENT_TIMESTAMP WHERE user_id=?", (row['user_id'],))
        return self.user(row['user_id'])

    def user(self,user_id):
        with self._connect() as c:
            return c.execute("SELECT * FROM beta_users WHERE user_id=?", (user_id,)).fetchone()

    def user_by_email(self,email):
        with self._connect() as c:
            return c.execute("SELECT * FROM beta_users WHERE email=? COLLATE NOCASE", (str(email or '').strip(),)).fetchone()

    def _expire_invites(self, c):
        c.execute("UPDATE beta_invites SET status='expired' WHERE status='pending' AND expires_at<=?", (self.now(),))
        c.execute("UPDATE beta_password_resets SET status='expired' WHERE status='pending' AND expires_at<=?", (self.now(),))

    def list_users(self):
        with self._connect() as c:
            self._expire_invites(c)
            return [dict(r) for r in c.execute("""SELECT u.user_id,u.email,u.display_name,u.is_owner,u.active,u.account_status,
                     u.password_set_at,u.terms_version,u.privacy_version,u.accepted_at,u.welcome_seen_at,u.created_at,u.last_login,
                     CASE WHEN i.user_id IS NULL THEN 0 ELSE 1 END AS icloud_saved,
                     inv.invite_id,inv.status AS invite_status,inv.expires_at AS invite_expires_at,
                     inv.delivery_status AS invite_delivery_status,inv.delivery_attempts AS invite_delivery_attempts,
                     inv.last_delivery_error AS invite_delivery_error
                     FROM beta_users u
                     LEFT JOIN beta_icloud_credentials i ON i.user_id=u.user_id
                     LEFT JOIN beta_invites inv ON inv.invite_id=(SELECT bi.invite_id FROM beta_invites bi WHERE bi.user_id=u.user_id ORDER BY bi.created_at DESC LIMIT 1)
                     ORDER BY u.is_owner DESC,u.created_at,u.email""")]

    def audit(self,event_type,outcome,user_id=None,invite_id=None,reset_id=None,reason='',request_id='',details=None):
        safe = details if isinstance(details, dict) else {}
        # Explicit allow-list: secrets/password/code/hash fields can never enter audit JSON.
        blocked = {'password','password_hash','invite_code','code','code_hash','reset_code','reset_hash','smtp_credential','oauth_token','access_token','refresh_token'}
        safe = {str(k):v for k,v in safe.items() if str(k).lower() not in blocked}
        event_id = 'aud_' + secrets.token_hex(12)
        with self._connect() as c:
            c.execute("INSERT INTO beta_audit_events(event_id,event_type,user_id,invite_id,reset_id,outcome,reason,request_id,details_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                      (event_id,event_type,user_id,invite_id,reset_id,outcome,str(reason or '')[:120],str(request_id or '')[:120],json.dumps(safe)[:2000],self.now()))
        return event_id

    def audit_events(self,limit=100):
        with self._connect() as c:
            return [dict(r) for r in c.execute("SELECT * FROM beta_audit_events ORDER BY created_at DESC LIMIT ?", (int(limit),))]

    def _rate_subject(self, value: str) -> str:
        return self.digest(str(value or '').strip().casefold())

    def rate_check_and_record(self,bucket:str,subject:str,limit:int,window:int,retry_message='Too many requests. Try again later.'):
        now = self.now(); cutoff = now-window; subject_hash=self._rate_subject(subject)
        with self._connect() as c:
            c.execute("DELETE FROM beta_rate_events WHERE created_at<?", (now-2*24*3600,))
            row = c.execute("SELECT COUNT(*) AS n,MIN(created_at) AS first FROM beta_rate_events WHERE bucket=? AND subject_hash=? AND created_at>?",
                            (bucket,subject_hash,cutoff)).fetchone()
            if row['n'] >= limit:
                retry=max(1,window-(now-int(row['first'] or now)))
                raise BetaError(retry_message,'too_many_requests',429,retry)
            c.execute("INSERT INTO beta_rate_events(bucket,subject_hash,created_at) VALUES(?,?,?)", (bucket,subject_hash,now))

    def _idempotency_lookup(self,owner_id,key,operation,request_payload):
        if not key: return None
        key_hash=self.digest(str(key)); req_hash=self.digest(json.dumps(request_payload,sort_keys=True,separators=(',',':')))
        mem=self.idempotency_memory.get(key_hash)
        if mem and mem[0] > time.time():
            _, stored_req, response, status = mem
            if stored_req != req_hash: raise BetaError('That idempotency key was already used for a different request.','idempotency_conflict',409)
            out=dict(response); out['replayed']=True
            return out,status
        with self._connect() as c:
            c.execute("DELETE FROM beta_idempotency WHERE created_at<?", (self.now()-IDEMPOTENCY_SECONDS,))
            row=c.execute("SELECT * FROM beta_idempotency WHERE key_hash=?", (key_hash,)).fetchone()
            if not row: return None
            if row['owner_user_id'] != owner_id or row['operation'] != operation or row['request_hash'] != req_hash:
                raise BetaError('That idempotency key was already used for a different request.','idempotency_conflict',409)
            response=json.loads(row['response_json'] or '{}')
            response['replayed']=True
            # Plaintext invite codes are intentionally not persisted for replay.
            response.pop('invite_code',None)
            return response,int(row['http_status'])

    def _idempotency_save(self,owner_id,key,operation,request_payload,response,status,result_id=''):
        if not key: return
        key_hash=self.digest(str(key)); req_hash=self.digest(json.dumps(request_payload,sort_keys=True,separators=(',',':')))
        safe=dict(response); safe.pop('invite_code',None); safe.pop('reset_code',None)
        with self._connect() as c:
            c.execute("INSERT OR REPLACE INTO beta_idempotency(key_hash,owner_user_id,operation,request_hash,result_id,http_status,response_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
                      (key_hash,owner_id,operation,req_hash,str(result_id or ''),int(status),json.dumps(safe),self.now()))
        # The plaintext secret is never retained for idempotency replay. A repeated
        # request receives the same operation/result ID but cannot reveal the code again.
        self.idempotency_memory[key_hash]=(time.time()+IDEMPOTENCY_SECONDS,req_hash,safe,int(status))

    def finalize_idempotency(self,owner_id,key,operation,request_payload,response,status,result_id=''):
        """Update the stored idempotent result after out-of-transaction work (email)."""
        if key:
            self._idempotency_save(owner_id,key,operation,request_payload,response,status,result_id)

    def _create_pending_user(self,email,display_name,apply_owner_template):
        email=str(email or '').strip().casefold(); display_name=str(display_name or '').strip()[:120]
        if '@' not in email or len(email)>254: raise BetaError('Enter a valid tester email address.')
        if postgres_enabled() and not os.environ.get('DATABASE_URL', '').strip():
            raise BetaError('DATABASE_URL is required for hosted tester storage.', 'hosted_storage_unavailable', 503)
        existing=self.user_by_email(email)
        if existing:
            raise BetaError('That email already has beta access or a pending invitation.','account_exists',409)
        uid=secrets.token_hex(12); rel=Path('beta_data')/f'{uid}.sqlite3'; path=self.root/rel
        if postgres_enabled():
            from postgres_support import provision_tester_schema
            provision_tester_schema(path)
        self.initialise_database_at(path)
        apply_owner_template(path)
        placeholder=self.digest(secrets.token_urlsafe(32))
        try:
            with self._connect() as c:
                c.execute("INSERT INTO beta_users(user_id,email,display_name,invite_hash,database_path,account_status) VALUES(?,?,?,?,?,'pending')",
                          (uid,email,display_name,placeholder,str(rel)))
        except sqlite3.IntegrityError as e:
            if postgres_enabled():
                from postgres_support import delete_tester_schema
                delete_tester_schema(path, uid)
            else:
                path.unlink(missing_ok=True)
            raise BetaError('That email already has beta access.','account_exists',409) from e
        return self.user(uid)

    def create_invite(self,email,display_name,apply_owner_template,owner_id,idempotency_key=''):
        with self.lock:
            return self._create_invite_locked(email,display_name,apply_owner_template,owner_id,idempotency_key)

    def _create_invite_locked(self,email,display_name,apply_owner_template,owner_id,idempotency_key=''):
        payload={'email':str(email or '').strip().casefold(),'display_name':str(display_name or '').strip()}
        replay=self._idempotency_lookup(owner_id,idempotency_key,'invite_create',payload)
        if replay: return replay
        self.rate_check_and_record('invite_email',payload['email'],3,3600,'Too many invites have been sent to this address. Try again later.')
        self.rate_check_and_record('invite_email_day',payload['email'],6,24*3600,'Daily invite limit reached for this address.')
        self.rate_check_and_record('owner_invite_hour',owner_id,20,3600,'Owner invite limit reached. Try again later.')
        self.rate_check_and_record('owner_invite_day',owner_id,100,24*3600,'Owner daily invite limit reached.')
        row=self._create_pending_user(payload['email'],payload['display_name'],apply_owner_template)
        code=self.new_code('ALIGN'); now=self.now(); invite_id='inv_'+secrets.token_hex(12)
        with self._connect() as c:
            c.execute("INSERT INTO beta_invites(invite_id,user_id,code_hash,status,created_at,expires_at,created_by_user_id) VALUES(?,?,?,'pending',?,?,?)",
                      (invite_id,row['user_id'],self.digest(self.canonical_code(code)),now,now+INVITE_SECONDS,owner_id))
            c.execute("UPDATE beta_users SET invite_hash=? WHERE user_id=?", (self.digest(self.canonical_code(code)),row['user_id']))
        response={'invite_id':invite_id,'invite_code':code,'expires_at':self.iso(now+INVITE_SECONDS),'status':'pending','user':self.public_user(row)}
        self._idempotency_save(owner_id,idempotency_key,'invite_create',payload,response,201,invite_id)
        self.audit('invite_created','success',row['user_id'],invite_id=invite_id,reason='owner_create')
        return response,201

    def invite(self,invite_id):
        with self._connect() as c:
            self._expire_invites(c)
            return c.execute("SELECT * FROM beta_invites WHERE invite_id=?",(invite_id,)).fetchone()

    def update_invite_delivery(self,invite_id,status,attempts,error=''):
        if status not in {'not_attempted','sending','retry_wait','sent','failed','not_confirmed'}:
            raise BetaError('Invalid invite delivery state.')
        with self._connect() as c:
            c.execute("UPDATE beta_invites SET delivery_status=?,delivery_attempts=?,last_delivery_at=?,last_delivery_error=? WHERE invite_id=?",
                      (status,int(attempts),self.now(),str(error or '')[:300],invite_id))

    def replace_invite(self,invite_id,owner_id,idempotency_key=''):
        with self.lock:
            return self._replace_invite_locked(invite_id,owner_id,idempotency_key)

    def _replace_invite_locked(self,invite_id,owner_id,idempotency_key=''):
        request={'invite_id':invite_id}
        replay=self._idempotency_lookup(owner_id,idempotency_key,'invite_replace',request)
        if replay: return replay
        # Rate checks must run before BEGIN IMMEDIATE so they do not open a second
        # writer connection while the replacement transaction holds SQLite's lock.
        with self._connect() as lookup:
            preview=lookup.execute("SELECT i.*,u.email,u.display_name,u.account_status FROM beta_invites i JOIN beta_users u ON u.user_id=i.user_id WHERE i.invite_id=?",(invite_id,)).fetchone()
        if not preview: raise BetaError('Invite not found.','invite_not_found',404)
        self.rate_check_and_record('invite_email',preview['email'],3,3600,'Too many invites have been sent to this address. Try again later.')
        self.rate_check_and_record('invite_email_day',preview['email'],6,24*3600,'Daily invite limit reached for this address.')
        self.rate_check_and_record('owner_invite_hour',owner_id,20,3600,'Owner invite limit reached. Try again later.')
        self.rate_check_and_record('owner_invite_day',owner_id,100,24*3600,'Owner daily invite limit reached.')
        with self.lock, self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            self._expire_invites(c)
            old=c.execute("SELECT i.*,u.email,u.display_name,u.account_status FROM beta_invites i JOIN beta_users u ON u.user_id=i.user_id WHERE i.invite_id=?",(invite_id,)).fetchone()
            if not old: raise BetaError('Invite not found.','invite_not_found',404)
            if old['status']!='pending': raise BetaError('That invite can no longer be replaced.','invite_unavailable',409)
            # Minimum 30 seconds between manual replacements for one tester.
            recent=c.execute("SELECT MAX(created_at) FROM beta_invites WHERE user_id=?",(old['user_id'],)).fetchone()[0] or 0
            if self.now()-int(recent)<30:
                raise BetaError('Wait 30 seconds before replacing this invite again.','too_many_requests',429,30-(self.now()-int(recent)))
            code=self.new_code('ALIGN'); now=self.now(); new_id='inv_'+secrets.token_hex(12)
            changed=c.execute("UPDATE beta_invites SET status='replaced',replaced_at=?,replaced_by_invite_id=NULL WHERE invite_id=? AND status='pending'",
                              (now,invite_id)).rowcount
            if changed!=1: raise BetaError('That invite changed while this request was being processed.','invite_already_used',409)
            c.execute("INSERT INTO beta_invites(invite_id,user_id,code_hash,status,created_at,expires_at,created_by_user_id) VALUES(?,?,?,'pending',?,?,?)",
                      (new_id,old['user_id'],self.digest(self.canonical_code(code)),now,now+INVITE_SECONDS,owner_id))
            c.execute("UPDATE beta_invites SET replaced_by_invite_id=? WHERE invite_id=?",(new_id,invite_id))
            c.execute("UPDATE beta_users SET invite_hash=? WHERE user_id=?",(self.digest(self.canonical_code(code)),old['user_id']))
        response={'old_invite_id':invite_id,'invite_id':new_id,'invite_code':code,'expires_at':self.iso(now+INVITE_SECONDS),'status':'pending','user_id':old['user_id'],'email':old['email'],'display_name':old['display_name']}
        self._idempotency_save(owner_id,idempotency_key,'invite_replace',request,response,201,new_id)
        self.audit('invite_replaced','success',old['user_id'],invite_id=new_id,reason='owner_replace',details={'old_invite_id':invite_id})
        return response,201

    def revoke_invite(self,invite_id,owner_id=''):
        with self.lock, self._connect() as c:
            c.execute('BEGIN IMMEDIATE'); self._expire_invites(c)
            row=c.execute("SELECT * FROM beta_invites WHERE invite_id=?",(invite_id,)).fetchone()
            if not row: raise BetaError('Invite not found.','invite_not_found',404)
            if row['status']=='used': raise BetaError('That invite has already been used.','invite_already_used',409)
            if row['status']!='pending': raise BetaError('That invite is no longer active.','invite_unavailable',409)
            changed=c.execute("UPDATE beta_invites SET status='revoked',revoked_at=? WHERE invite_id=? AND status='pending'",(self.now(),invite_id)).rowcount
            if changed!=1: raise BetaError('That invite changed while this request was being processed.','invite_unavailable',409)
        self.audit('invite_revoked','success',row['user_id'],invite_id=invite_id,reason='owner_revoke')
        return {'invite_id':invite_id,'status':'revoked'}

    def validate_invite(self,email,code):
        email=str(email or '').strip().casefold(); digest=self.digest(self.canonical_code(code)); now=self.now()
        with self._connect() as c:
            self._expire_invites(c)
            row=c.execute("""SELECT i.*,u.email,u.display_name FROM beta_invites i JOIN beta_users u ON u.user_id=i.user_id
                             WHERE u.email=? AND i.code_hash=? AND u.active=1 AND u.account_status='pending'""",(email,digest)).fetchone()
            return row if row and row['status']=='pending' and int(row['expires_at'])>now else None

    def complete_invite(self,email,code,password,remote=''):
        self.validate_password(password)
        email=str(email or '').strip().casefold(); code_hash=self.digest(self.canonical_code(code)); now=self.now()
        pw_hash=self.hash_password(password)
        with self.lock, self._connect() as c:
            c.execute('BEGIN IMMEDIATE'); self._expire_invites(c)
            invite=c.execute("""SELECT i.*,u.email,u.account_status FROM beta_invites i JOIN beta_users u ON u.user_id=i.user_id
                                WHERE u.email=? AND i.code_hash=? AND u.active=1 AND u.account_status='pending'""",(email,code_hash)).fetchone()
            if not invite or invite['status']!='pending' or int(invite['expires_at'])<=now:
                raise BetaError('That invite is unavailable.','invite_unavailable',400)
            changed=c.execute("UPDATE beta_invites SET status='used',used_at=? WHERE invite_id=? AND status='pending' AND expires_at>?",
                              (now,invite['invite_id'],now)).rowcount
            if changed!=1:
                raise BetaError('That invite has already been used.','invite_already_used',409)
            account_changed=c.execute("UPDATE beta_users SET password_hash=?,password_set_at=CURRENT_TIMESTAMP,account_status='active',invite_hash=? WHERE user_id=? AND account_status='pending'",
                      (pw_hash,self.digest(secrets.token_urlsafe(32)),invite['user_id'])).rowcount
            if account_changed != 1:
                raise BetaError('Account setup could not be completed.','invite_unavailable',409)
            row=c.execute("SELECT * FROM beta_users WHERE user_id=?",(invite['user_id'],)).fetchone()
            token=self._new_session(c,row)
        self.audit('invite_redeemed','success',invite['user_id'],invite_id=invite['invite_id'],reason='account_created')
        return self.by_session(token),token

    def public_user(self,row):
        if not row: return None
        return {'user_id':row['user_id'],'email':row['email'],'display_name':row['display_name'],'is_owner':bool(row['is_owner']),
                'active':bool(row['active']),'account_status':row['account_status'],'password_set':bool(row['password_hash'])}

    def set_active(self,user_id,active):
        row=self.user(user_id)
        if not row or row['is_owner']: raise BetaError('The owner account cannot be disabled here.')
        with self._connect() as c:
            c.execute("UPDATE beta_users SET active=?,session_hash='',session_expires=0 WHERE user_id=?",(1 if active else 0,user_id))
            if not active: c.execute("DELETE FROM beta_sessions WHERE user_id=?", (user_id,))
        self.audit('account_enabled' if active else 'account_disabled','success',user_id,reason='owner_action')
        return dict(self.user(user_id))

    def reset_invite(self,user_id):
        """Compatibility helper for owner setup / old Admin buttons.

        Pending V3.0 testers receive a replacement invite. Established accounts receive
        a one-time password-reset code instead of having their password exposed.
        """
        row=self.user(user_id)
        if not row: raise BetaError('Tester not found.')
        if row['is_owner'] and not row['password_hash']:
            code=self.new_code('OWNER')
            with self._connect() as c:
                c.execute("UPDATE beta_users SET invite_hash=?,session_hash='',session_expires=0 WHERE user_id=?",(self.digest(self.canonical_code(code)),user_id))
                c.execute("DELETE FROM beta_sessions WHERE user_id=?",(user_id,))
            return code
        if row['account_status']=='pending':
            with self._connect() as c:
                active=c.execute("SELECT invite_id FROM beta_invites WHERE user_id=? AND status='pending' ORDER BY created_at DESC LIMIT 1",(user_id,)).fetchone()
            if active:
                return self.replace_invite(active['invite_id'], self.owner()['user_id'])[0]['invite_code']
        code, _ = self.create_password_reset_for_user(user_id)
        return code

    def delete_user(self,user_id):
        row=self.user(user_id)
        if not row or row['is_owner']: raise BetaError('The owner account cannot be removed here.')
        path=self.database_for(row)
        if postgres_enabled():
            from postgres_support import delete_tester_schema
            delete_tester_schema(path, user_id)
        else:
            with self._connect() as c: c.execute("DELETE FROM beta_users WHERE user_id=?",(user_id,))
            path.unlink(missing_ok=True)
        self.audit('account_removed','success',user_id,reason='owner_action')

    def add_feedback(self,row,kind,message,build,screen=''):
        kind=str(kind or 'general').lower()
        if kind not in {'problem','idea','general'}: raise BetaError('Choose Problem, Idea or General feedback.')
        message=str(message or '').strip()[:4000]
        if not message: raise BetaError('Write a short message before sending feedback.')
        with self._connect() as c:
            c.execute("INSERT INTO beta_feedback(user_id,feedback_type,message,build_version,screen) VALUES(?,?,?,?,?)",
                      (row['user_id'],kind,message,int(build),str(screen or '')[:120]))

    def feedback(self,limit=200):
        with self._connect() as c:
            return [dict(r) for r in c.execute("""SELECT f.id,f.feedback_type,f.message,f.build_version,f.screen,f.created_at,u.email
                  FROM beta_feedback f JOIN beta_users u ON u.user_id=f.user_id ORDER BY f.id DESC LIMIT ?""",(limit,))]

    # ----- Password recovery -----
    def _new_reset(self,user_id):
        now=self.now(); code=self.new_code('RESET'); reset_id='rst_'+secrets.token_hex(12)
        with self.lock,self._connect() as c:
            c.execute('BEGIN IMMEDIATE'); self._expire_invites(c)
            old=c.execute("SELECT reset_id FROM beta_password_resets WHERE user_id=? AND status='pending' ORDER BY created_at DESC LIMIT 1",(user_id,)).fetchone()
            if old:
                c.execute("UPDATE beta_password_resets SET status='replaced',replaced_at=?,replaced_by_reset_id=NULL WHERE reset_id=? AND status='pending'",
                          (now,old['reset_id']))
            c.execute("INSERT INTO beta_password_resets(reset_id,user_id,code_hash,status,created_at,expires_at) VALUES(?,?,?,'pending',?,?)",
                      (reset_id,user_id,self.digest(self.canonical_code(code)),now,now+RESET_SECONDS))
            if old:
                c.execute("UPDATE beta_password_resets SET replaced_by_reset_id=? WHERE reset_id=?",(reset_id,old['reset_id']))
        return code,reset_id

    def create_password_reset_for_user(self,user_id):
        row=self.user(user_id)
        if not row or not row['active'] or row['account_status']!='active': raise BetaError('Account not available.','account_unavailable',409)
        return self._new_reset(user_id)

    def request_password_reset(self,identifier,remote=''):
        ident=str(identifier or '').strip().casefold()
        self.rate_check_and_record('forgot_identifier',ident,3,3600,'Too many password-reset requests. Try again later.')
        self.rate_check_and_record('forgot_ip',remote or 'unknown',10,3600,'Too many password-reset requests. Try again later.')
        row=self.user_by_email(ident)
        if not row or not row['active'] or row['account_status']!='active' or not row['password_hash']:
            self.audit('password_reset_requested','success',reason='privacy_safe_no_match')
            return None,None,None
        code,reset_id=self._new_reset(row['user_id'])
        self.audit('password_reset_requested','success',row['user_id'],reset_id=reset_id,reason='reset_requested')
        return row,code,reset_id

    def update_reset_delivery(self,reset_id,status,attempts,error=''):
        with self._connect() as c:
            c.execute("UPDATE beta_password_resets SET delivery_status=?,delivery_attempts=?,last_delivery_at=?,last_delivery_error=? WHERE reset_id=?",
                      (status,int(attempts),self.now(),str(error or '')[:300],reset_id))

    def reset_password(self,code,password,remote=''):
        self.validate_password(password)
        canonical=self.canonical_code(code); key=f"{remote}|{self.digest(canonical)}"
        self._attempt_check(self.reset_attempts,key)
        code_hash=self.digest(canonical); now=self.now(); pw_hash=self.hash_password(password)
        with self.lock,self._connect() as c:
            c.execute('BEGIN IMMEDIATE'); self._expire_invites(c)
            reset=c.execute("SELECT * FROM beta_password_resets WHERE code_hash=?",(code_hash,)).fetchone()
            if not reset or reset['status']!='pending' or int(reset['expires_at'])<=now:
                self._attempt_fail(self.reset_attempts,key)
                raise BetaError('That reset code is unavailable.','reset_code_unavailable',400)
            changed=c.execute("UPDATE beta_password_resets SET status='used',used_at=? WHERE reset_id=? AND status='pending' AND expires_at>?",
                              (now,reset['reset_id'],now)).rowcount
            if changed!=1:
                self._attempt_fail(self.reset_attempts,key)
                raise BetaError('That reset code has already been used.','reset_code_already_used',409)
            c.execute("UPDATE beta_users SET password_hash=?,password_set_at=CURRENT_TIMESTAMP WHERE user_id=? AND active=1",
                      (pw_hash,reset['user_id']))
            revoked=c.execute("SELECT COUNT(*) FROM beta_sessions WHERE user_id=?",(reset['user_id'],)).fetchone()[0]
            c.execute("DELETE FROM beta_sessions WHERE user_id=?",(reset['user_id'],))
            c.execute("UPDATE beta_users SET session_hash='',session_expires=0 WHERE user_id=?",(reset['user_id'],))
        self._attempt_success(self.reset_attempts,key)
        self.audit('password_reset_completed','success',reset['user_id'],reset_id=reset['reset_id'],reason='reset_completed',details={'sessions_revoked':int(revoked)})
        return {'password_reset':True,'sessions_revoked':True,'session_count_revoked':int(revoked),'next_step':'sign_in'}

    # ----- Outlook OAuth2 SMTP settings -----
    def get_email_settings_internal(self):
        with self._connect() as c:
            return dict(c.execute("SELECT * FROM beta_email_settings WHERE singleton=1").fetchone())

    def email_settings_public(self):
        s=self.get_email_settings_internal()
        return {'configured':bool(s['sender_email'] and s['oauth_client_id']),'sender_email':s['sender_email'] or None,
                'sender_name':s['sender_name'] or None,'smtp_host':s['smtp_host'],'smtp_port':s['smtp_port'],
                'encryption':s['encryption'],'oauth_client_id':s['oauth_client_id'] or None,'oauth_authority':s['oauth_authority'],
                'credential_saved':bool(s['oauth_cache_enc']),'connection_status':s['connection_status'],
                'last_checked_at':s['last_checked_at'] or None,'last_success_at':s['last_success_at'] or None,
                'last_error':s['last_error'] or None}

    def save_email_settings(self,payload):
        email=str(payload.get('sender_email','')).strip().casefold(); name=str(payload.get('sender_name','Align')).strip()[:100]
        client_id=str(payload.get('oauth_client_id','')).strip()[:200]; authority=str(payload.get('oauth_authority','consumers')).strip()[:80] or 'consumers'
        if '@' not in email: raise BetaError('Enter the Outlook sender email address.','invalid_email_settings')
        if not client_id: raise BetaError('Enter the Microsoft application Client ID.','invalid_email_settings')
        # V3.0 intentionally pins Outlook.com SMTP's published TLS endpoint.
        with self._connect() as c:
            old=c.execute("SELECT oauth_client_id,sender_email FROM beta_email_settings WHERE singleton=1").fetchone()
            clear_cache = old and (old['oauth_client_id']!=client_id or old['sender_email'].casefold()!=email)
            c.execute("""UPDATE beta_email_settings SET sender_email=?,sender_name=?,smtp_host='smtp-mail.outlook.com',smtp_port=587,
                         encryption='starttls',oauth_client_id=?,oauth_authority=?,oauth_cache_enc=CASE WHEN ? = 1 THEN '' ELSE oauth_cache_enc END,
                         connection_status='untested',last_error='',updated_at=CURRENT_TIMESTAMP WHERE singleton=1""",
                      (email,name or 'Align',client_id,authority,1 if clear_cache else 0))
        self.audit('email_settings_updated','success',self.owner()['user_id'] if self.owner() else None,reason='owner_action')
        return self.email_settings_public()

    def set_email_token_cache(self, cache_text: str):
        f=self._fernet(); enc=f.encrypt(cache_text.encode()).decode()
        with self._connect() as c:
            c.execute("UPDATE beta_email_settings SET oauth_cache_enc=?,connection_status='connected',last_checked_at=CURRENT_TIMESTAMP::text,last_success_at=CURRENT_TIMESTAMP::text,last_error='',updated_at=CURRENT_TIMESTAMP WHERE singleton=1",(enc,))

    def load_email_token_cache(self):
        s=self.get_email_settings_internal(); value=s.get('oauth_cache_enc','')
        if not value: return ''
        try: return self._fernet().decrypt(value.encode()).decode()
        except Exception: raise BetaError('Saved Outlook connection cannot be decrypted on this server.','email_connection_failed',503) from None

    def set_email_status(self,status,error=''):
        allowed={'not_configured','untested','connected','authentication_failed','connection_failed','tls_failed','provider_rejected'}
        if status not in allowed: status='connection_failed'
        with self._connect() as c:
            c.execute("UPDATE beta_email_settings SET connection_status=?,last_checked_at=CURRENT_TIMESTAMP::text,last_success_at=CASE WHEN ?='connected' THEN CURRENT_TIMESTAMP::text ELSE last_success_at END,last_error=?,updated_at=CURRENT_TIMESTAMP WHERE singleton=1",
                      (status,status,str(error or '')[:300]))

    # ----- Existing encrypted iCloud credentials -----
    def _fernet(self):
        try: from cryptography.fernet import Fernet
        except ImportError: raise BetaError('Run Install Align Add-ons.bat and choose Owner accounts and remote access before using encrypted account credentials.','beta_support_missing',503) from None
        configured = os.environ.get('ALIGN_CREDENTIAL_KEY', '').strip()
        if configured:
            try:
                return Fernet(configured.encode('ascii'))
            except (ValueError, UnicodeError):
                raise BetaError('The saved-credential key is invalid. Contact the Owner.', 'credential_key_unavailable', 503) from None
        if postgres_enabled():
            raise BetaError('A persistent saved-credential key must be configured before connecting iCloud.', 'credential_key_unavailable', 503)
        if not self.secret_file.exists():
            self.secret_file.write_bytes(Fernet.generate_key())
            try: os.chmod(self.secret_file,0o600)
            except OSError: pass
        return Fernet(self.secret_file.read_bytes().strip())

    def public_key(self):
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import rsa
        except ImportError: raise BetaError('Run Install Align Add-ons.bat and choose Owner accounts and remote access first.','beta_support_missing',503) from None
        if not self.rsa_private_file.exists():
            private=rsa.generate_private_key(public_exponent=65537,key_size=3072)
            self.rsa_private_file.write_bytes(private.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
            try: os.chmod(self.rsa_private_file,0o600)
            except OSError: pass
        private=serialization.load_pem_private_key(self.rsa_private_file.read_bytes(),password=None)
        der=private.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
        return base64.b64encode(der).decode('ascii')

    def decrypt_browser(self,value):
        try:
            from cryptography.hazmat.primitives import hashes,serialization
            from cryptography.hazmat.primitives.asymmetric import padding
            private=serialization.load_pem_private_key(self.rsa_private_file.read_bytes(),password=None)
            raw=private.decrypt(base64.b64decode(str(value)),padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),algorithm=hashes.SHA256(),label=None))
            return raw.decode('utf-8')
        except Exception as e: raise BetaError('The encrypted iCloud credential could not be read. Refresh and try again.','credential_error') from e

    def store_icloud(self,row,username,password):
        f=self._fernet(); ue=f.encrypt(username.encode()).decode(); pe=f.encrypt(password.encode()).decode()
        with self._connect() as c:
            c.execute("""INSERT INTO beta_icloud_credentials(user_id,username_enc,password_enc) VALUES(?,?,?)
                         ON CONFLICT(user_id) DO UPDATE SET username_enc=excluded.username_enc,password_enc=excluded.password_enc,updated_at=CURRENT_TIMESTAMP""",
                      (row['user_id'],ue,pe))

    def load_icloud(self,row):
        with self._connect() as c: saved=c.execute("SELECT username_enc,password_enc FROM beta_icloud_credentials WHERE user_id=?",(row['user_id'],)).fetchone()
        if not saved:return None
        f=self._fernet()
        try:return f.decrypt(saved['username_enc'].encode()).decode(),f.decrypt(saved['password_enc'].encode()).decode()
        except Exception: raise BetaError('Saved iCloud credentials cannot be decrypted on this server.','credential_error') from None

    def clear_icloud(self,row):
        with self._connect() as c: c.execute("DELETE FROM beta_icloud_credentials WHERE user_id=?",(row['user_id'],))
