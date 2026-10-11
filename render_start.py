"""Hosted Owner storage, or explicitly disposable SQLite smoke tests."""
import os
import tempfile
from pathlib import Path
from sqlite_support import postgres_enabled


def bootstrap_hosted_owner(store, password):
    # Serialize first-run bootstrap across simultaneous Render workers/restarts.
    with store._connect() as connection:
        connection.execute('SELECT pg_advisory_xact_lock(151202609)')
        owners = connection.execute('SELECT * FROM beta_users WHERE is_owner=1 FOR UPDATE').fetchall()
        if len(owners) > 1:
            raise RuntimeError('Hosted startup requires exactly one Owner in align_auth')
        if owners and owners[0]['password_hash']:
            return
        if len(password) < 20:
            raise RuntimeError('Set ALIGN_PREVIEW_PASSWORD of at least 20 characters to bootstrap the Owner')
        store.validate_password(password)
        password_hash = store.hash_password(password)
        if owners:
            connection.execute("UPDATE beta_users SET password_hash=?,password_set_at=CURRENT_TIMESTAMP WHERE user_id=? AND COALESCE(password_hash,'')=''",
                               (password_hash, owners[0]['user_id']))
        else:
            import secrets
            connection.execute("""INSERT INTO beta_users
                (user_id,email,invite_hash,database_path,is_owner,account_status,password_hash,password_set_at)
                VALUES(?,?,?,'align.sqlite3',1,'active',?,CURRENT_TIMESTAMP)""",
                (secrets.token_hex(12), 'preview@example.com', store.digest(secrets.token_urlsafe(40)), password_hash))


def prepare_preview():
    hosted = postgres_enabled()
    mode = os.environ.get('ALIGN_HOSTING_MODE', '').strip().lower()
    if hosted and mode != 'persistent':
        raise RuntimeError('PostgreSQL requires ALIGN_HOSTING_MODE=persistent.')
    if not hosted and mode != 'disposable-preview':
        raise RuntimeError('SQLite is allowed on Render only for ALIGN_HOSTING_MODE=disposable-preview.')
    password = os.environ.get('ALIGN_PREVIEW_PASSWORD', '')
    if not hosted and len(password) < 20:
        raise RuntimeError('Set a strong ALIGN_PREVIEW_PASSWORD of at least 20 characters')
    os.environ['ALIGN_BETA_MODE'] = '1'
    # Hosted journeys require the reviewed HERE setup and durable quota storage.
    os.environ['ALIGN_TRANSPORT_ENABLED'] = '1' if (
        hosted and os.environ.get('ALIGN_JOURNEY_PROVIDER') == 'here'
        and os.environ.get('ALIGN_HERE_TRANSIT_ENABLED') == '1'
        and os.environ.get('ALIGN_HERE_ROUTING_KEY')
    ) else '0'
    import app
    from beta_support import BetaStore
    if hosted:
        # Postgres mode uses Neon schemas selected from the logical database
        # paths; no local SQLite file or local credentials are imported.
        app.BETA_MODE = True
        app.DATABASE = Path('align.sqlite3')
        from postgres_support import prepare_calendar_locations
        prepare_calendar_locations()
        app.initialise_database()
        app.BETA_STORE = BetaStore(app.ROOT, app.DATABASE, app.initialise_database_at)
        bootstrap_hosted_owner(app.BETA_STORE, password)
        if os.environ['ALIGN_TRANSPORT_ENABLED'] == '1':
            from transport_service import prepare_hosted_storage
            prepare_hosted_storage()
        from postgres_support import verify_hosted_storage
        verify_hosted_storage()
        return app, None
    # Always create a fresh runtime, even on a host that happens to retain files.
    # Never read the source-tree SQLite databases or copy local credentials.
    runtime = tempfile.TemporaryDirectory(prefix='align-preview-')
    try:
        BetaStore.validate_password(password)
        app.BETA_MODE = True
        app.DATABASE = Path(runtime.name) / 'align.sqlite3'
        app.initialise_database()
        app.BETA_STORE = BetaStore(Path(runtime.name), app.DATABASE, app.initialise_database_at)
        owner, _ = app.BETA_STORE.ensure_owner('preview@example.com')
        password_hash = app.BETA_STORE.hash_password(password)
        with app.BETA_STORE._connect() as connection:
            connection.execute('UPDATE beta_users SET password_hash=?,password_set_at=CURRENT_TIMESTAMP WHERE user_id=?',
                               (password_hash, owner['user_id']))
        return app, runtime
    except Exception:
        runtime.cleanup()
        raise


def main():
    app, runtime = prepare_preview()
    try:
        with app.AlignServer(('0.0.0.0', int(os.environ.get('PORT', '10000'))), app.AlignHandler) as server:
            if os.environ.get('ALIGN_DATABASE_BACKEND', 'sqlite').strip().lower() == 'postgres':
                print('Align V3.0 persistent service ready: Neon storage verified.', flush=True)
            else:
                print('Align V3.0 disposable preview ready. Data resets on every restart.', flush=True)
            server.serve_forever()
    finally:
        if runtime is not None:
            runtime.cleanup()


if __name__ == '__main__':
    main()
