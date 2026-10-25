"""Create or verify the Align V3 Owner in the explicitly selected live Postgres DB."""
from __future__ import annotations

import getpass
import json
import os
import secrets
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
EXPECTED_PUBLIC_URL = "https://www.getalign.co.uk"
EXPECTED_BUILD = 156
EXPECTED_DATABASE = "align_v3"
EXPECTED_DATABASE_ROLE = "align_v3_owner"
BOOTSTRAP_OWNER_EMAIL = "preview@example.com"


def live_status(base_url: str) -> dict:
    request = Request(base_url.rstrip("/") + "/api/beta/status", headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=15) as response:
            if response.status != 200:
                raise RuntimeError(f"Live status returned HTTP {response.status}.")
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise RuntimeError(f"Could not verify the live Align V3 authentication endpoint ({type(exc).__name__}).") from None
    if payload.get("beta") is not True:
        raise RuntimeError("The selected live URL is not serving Align beta authentication.")
    if int(payload.get("build_version", -1)) != EXPECTED_BUILD:
        raise RuntimeError(
            f"Live build {payload.get('build_version')!r} does not match this setup tool's V3 build {EXPECTED_BUILD}."
        )
    return payload


def authenticate_live(base_url: str, email: str, password: str) -> bool:
    origin = base_url.rstrip("/")
    body = json.dumps({"email": email, "password": password}).encode("utf-8")
    request = Request(
        origin + "/api/beta/login", data=body, method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json", "Origin": origin},
    )
    try:
        with urlopen(request, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))
            cookies = response.headers.get_all("Set-Cookie") or []
            token = next((part.strip().split(";", 1)[0] for part in cookies if part.strip().startswith("align_beta=")), "")
    except HTTPError as exc:
        raise RuntimeError(f"Live login verification failed with HTTP {exc.code}.") from None
    except (URLError, TimeoutError, ValueError) as exc:
        raise RuntimeError(f"Could not complete live login verification ({type(exc).__name__}).") from None
    user = result.get("user") or {}
    if user.get("email", "").casefold() != email.casefold() or user.get("is_owner") is not True or not user.get("password_set"):
        raise RuntimeError("Live login succeeded, but the returned identity does not have verified Owner permissions.")
    if not token:
        raise RuntimeError("Live login did not return the expected Align session cookie.")
    try:
        me_request = Request(origin + "/api/beta/me", headers={"Cookie": token, "Accept": "application/json"})
        with urlopen(me_request, timeout=15) as response:
            me = json.loads(response.read().decode("utf-8"))
        me_user = me.get("user") or {}
        if (not me.get("authenticated") or me_user.get("email", "").casefold() != email.casefold()
                or me_user.get("is_owner") is not True):
            raise RuntimeError("Live session did not resolve to the expected Owner account.")
        if not me.get("terms_version"):
            return False
        studio = Request(origin + "/management-studio", headers={"Cookie": token})
        with urlopen(studio, timeout=15) as response:
            studio_html = response.read().decode("utf-8", errors="replace")
            if response.status != 200 or "<title>Align · Management Studio</title>" not in studio_html:
                raise RuntimeError("The authenticated Owner could not open the deployed Management Studio.")
        return True
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"Could not verify Management Studio access ({type(exc).__name__}).") from None
    finally:
        logout = Request(
            origin + "/api/beta/logout", data=b"{}", method="POST",
            headers={"Content-Type": "application/json", "Origin": origin, "Cookie": token},
        )
        try:
            with urlopen(logout, timeout=15) as response:
                if response.status != 200:
                    raise RuntimeError("Live logout did not complete cleanly after verification.")
        except (HTTPError, URLError, TimeoutError) as exc:
            raise RuntimeError(f"Owner login worked, but session cleanup failed ({type(exc).__name__}).") from None


def main() -> int:
    print("Align V3 live Owner setup")
    print("This connects directly to the selected production Postgres database.")
    print("Live sign-in uses your Owner email and V3 password. A code created by local beta setup is not a live Owner credential.")
    base_url = input(f"Live application URL [{EXPECTED_PUBLIC_URL}]: ").strip() or EXPECTED_PUBLIC_URL
    if base_url.rstrip("/") != EXPECTED_PUBLIC_URL:
        print(f"Refusing unrecognized production URL. Expected {EXPECTED_PUBLIC_URL}.", file=sys.stderr)
        return 2
    if urlparse(base_url).scheme != "https":
        print("Refusing a non-HTTPS production URL.", file=sys.stderr)
        return 2
    try:
        status = live_status(base_url)
        print(f"Verified live authentication endpoint: Align V3.0 build {status['build_version']}.")
        print("Use the Neon production connection URI for database align_v3 and role align_v3_owner.")
        print("In Neon Console: Align V3.0 → production → align_v3 → Connect → Direct connection (no -pooler).")
        dsn = getpass.getpass("Production Postgres connection URI (input hidden): ").strip()
        if not dsn.startswith(("postgres://", "postgresql://")):
            raise RuntimeError("A PostgreSQL DATABASE_URL is required; SQLite is not accepted.")
        email = input("Owner login email: ").strip().casefold()
        if not email or "@" not in email:
            raise RuntimeError("Enter a valid owner email address.")
        password = getpass.getpass("Owner password (input hidden): ")
        confirm = getpass.getpass("Confirm owner password (input hidden): ")
        if password != confirm:
            raise RuntimeError("The passwords do not match.")

        os.environ["ALIGN_DATABASE_BACKEND"] = "postgres"
        os.environ["ALIGN_HOSTING_MODE"] = "persistent"
        os.environ["ALIGN_BETA_MODE"] = "1"
        os.environ["DATABASE_URL"] = dsn
        sys.path.insert(0, str(ROOT))
        import app
        from beta_support import BetaError, BetaStore
        app.BETA_MODE = True
        app.DATABASE = Path("align.sqlite3")
        store = BetaStore(app.ROOT, app.DATABASE, app.initialise_database_at)
        # Confirm the connection resolves to V3's owner auth schema before any writes.
        with store._connect() as connection:
            target = connection.execute(
                "SELECT current_database() AS database_name, current_user AS role_name, current_schema() AS schema_name"
            ).fetchone()
            if (target["database_name"] != EXPECTED_DATABASE
                    or target["role_name"] != EXPECTED_DATABASE_ROLE
                    or target["schema_name"] != "align_auth"):
                raise RuntimeError(
                    "The connection is not the Align V3 production database (expected align_v3 / "
                    "align_v3_owner / align_auth); no account was changed."
                )
            connection.execute("SELECT pg_advisory_xact_lock(151202609)")
            owners = connection.execute("SELECT * FROM beta_users WHERE is_owner=1 FOR UPDATE").fetchall()
            if len(owners) > 1:
                raise RuntimeError("Production auth contains more than one owner; refusing changes.")
            owner_id = owners[0]["user_id"] if owners else ""
            collision = connection.execute(
                "SELECT user_id FROM beta_users WHERE email=? AND user_id<>? LIMIT 1",
                (email, owner_id),
            ).fetchone()
            if collision:
                raise RuntimeError("That email is already assigned to another account; choose a different Owner email.")
            encoded = ""
            invite_hash = ""
            action = ""
            if owners:
                owner = owners[0]
                current_email = owner["email"].casefold()
                password_matches = bool(owner["password_hash"] and store.verify_password(owner["password_hash"], password))
                if current_email == email and password_matches:
                    print("Matching Owner account already exists; no database changes made.")
                elif current_email == email:
                    print("This Owner email already exists, but the entered password does not match.")
                    if input("To set the password you just entered for this Owner, type RESET: ").strip() != "RESET":
                        raise RuntimeError("Password was not changed; no account or password was changed.")
                    action = "reset"
                elif current_email == BOOTSTRAP_OWNER_EMAIL:
                    print("Production contains the default deployment Owner (preview@example.com).")
                    if input("To replace that placeholder with your Owner email and password, type REPLACE: ").strip() != "REPLACE":
                        raise RuntimeError("Placeholder Owner was left unchanged.")
                    action = "replace"
                else:
                    raise RuntimeError("A different Owner account already exists; no account or password was changed.")
            else:
                action = "create"

            if action:
                BetaStore.validate_password(password)
                encoded = store.hash_password(password)
                invite_hash = store.digest(secrets.token_urlsafe(40))
            if action == "create":
                uid = secrets.token_hex(12)
                connection.execute(
                    """INSERT INTO beta_users
                       (user_id,email,invite_hash,database_path,is_owner,account_status,password_hash,password_set_at)
                       VALUES(?,?,?,'align.sqlite3',1,'active',?,CURRENT_TIMESTAMP)""",
                    (uid, email, invite_hash, encoded),
                )
                print("Owner account created in production align_auth.beta_users with an Argon2 password hash.")
            elif action in {"replace", "reset"}:
                changed = connection.execute(
                    """UPDATE beta_users
                       SET email=?,invite_hash=?,session_hash='',session_expires=0,
                           password_hash=?,password_set_at=CURRENT_TIMESTAMP,account_status='active'
                       WHERE user_id=? AND is_owner=1""",
                    (email, invite_hash, encoded, owner["user_id"]),
                )
                if changed.rowcount != 1:
                    raise RuntimeError("The existing Owner changed during setup; no further changes were made.")
                connection.execute("DELETE FROM beta_sessions WHERE user_id=?", (owner["user_id"],))
                print("Owner account updated in production with an Argon2 password hash; previous sessions were revoked.")
        # Check the password through the same verifier used by the live login handler.
        owner = store.owner()
        if not owner or not owner["is_owner"] or not store.verify_password(owner["password_hash"], password):
            raise RuntimeError("Production owner/hash verification failed.")
        # Ensure this exact production DB is reachable by the deployed login endpoint.
        studio_access = authenticate_live(base_url, email, password)
        if studio_access:
            print("PASS: deployed login accepted the account, returned Owner permissions, opened Management Studio, and logged out.")
        else:
            print("OWNER LOGIN VERIFIED: the deployed app accepts this password and recognizes the Owner account.")
            print("One-time step: open https://www.getalign.co.uk, sign in, and accept the Terms & Privacy Notice.")
            print("Then open Management Studio. Owner access is gated until that notice is accepted.")
        return 0
    except (RuntimeError, ValueError) as exc:
        print(f"SETUP STOPPED: {exc}", file=sys.stderr)
        return 1
    finally:
        os.environ.pop("DATABASE_URL", None)


if __name__ == "__main__":
    raise SystemExit(main())
