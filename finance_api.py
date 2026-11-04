"""HTTP routes for the separate finance ledger."""
from __future__ import annotations

import logging
import re

import finance_db

LOG = logging.getLogger('align.finance')
_ENTRY = re.compile(r'^/api/finance/entries/(\d+)$')


def handle_get(handler, app, connection, path) -> bool:
    if path != '/api/finance':
        return False

    def send():
        _authorized(handler, app)
        with finance_db.connect(app.current_database()) as finance:
            handler.send_json(200, finance_db.summary(finance))

    return _guard(handler, send)


def handle_post(handler, app, path, payload) -> bool:
    if path not in {'/api/finance/entries', '/api/finance/import'}:
        return False

    def send():
        _authorized(handler, app)
        with finance_db.connect(app.current_database()) as finance:
            if path.endswith('/import'):
                created = finance_db.import_csv(finance, (payload or {}).get('csv') or '')
                handler.send_json(201, {'created': created, 'summary': finance_db.summary(finance)})
            else:
                handler.send_json(201, {'entry': finance_db.add_entry(finance, payload or {})})

    return _guard(handler, send)


def handle_patch(handler, app, path, payload) -> bool:
    if path != '/api/finance/settings':
        return False

    def send():
        _authorized(handler, app)
        with finance_db.connect(app.current_database()) as finance:
            handler.send_json(200, {'settings': finance_db.update_settings(finance, payload or {})})

    return _guard(handler, send)


def handle_delete(handler, app, path) -> bool:
    match = _ENTRY.fullmatch(path)
    if not match:
        return False

    def send():
        _authorized(handler, app)
        with finance_db.connect(app.current_database()) as finance:
            finance_db.delete_entry(finance, match.group(1))
            handler.send_json(200, {'ok': True})

    return _guard(handler, send)


def _authorized(handler, app) -> None:
    if not getattr(app, 'BETA_MODE', False):
        return
    row = handler.require_beta_user()
    if not row or not handler.beta_same_origin():
        raise finance_db.FinanceError('Sign in to open finance.', 'unauthorised', 401)


def _guard(handler, action) -> bool:
    try:
        action()
    except finance_db.FinanceError as error:
        LOG.info('finance request rejected code=%s', error.code)
        handler.send_json(error.status, {'error': str(error), 'code': error.code})
    except Exception:
        LOG.error('finance request failed')
        handler.send_json(500, {'error': 'The finance ledger could not be saved.', 'code': 'finance_failed'})
    return True
