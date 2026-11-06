"""Authenticated rota import routes.

Multipart uploads are read with a hard size cap before any JSON parser runs.
Responses never include temp paths, original filenames, file bytes or OCR text.
"""
from __future__ import annotations

import logging
import re

import rota_file_processor as files
import rota_ocr_provider
import work_rota_import
import work_rota_storage as storage

LOG = logging.getLogger('align.rota')

CAPABILITIES = {
    'csv': True,
    'xlsx': True,
    'pdf_text': True,
    'image_ocr': False,
    'scanned_pdf_ocr': False,
    'accepted_extensions': ['csv', 'xlsx', 'pdf', 'jpg', 'jpeg', 'png', 'heic', 'heif'],
}

_MESSAGES = {
    'ocr_unavailable': 'Local OCR is unavailable. Install Tesseract OCR with its English language data to read photos and scanned PDFs.',
    'ocr_no_text': 'No readable rota text was found in this file. Try a clearer, well-lit photo or a higher-quality scan.',
    'ocr_failed': 'The local OCR engine could not process this file. Try a clearer image or a text-based rota.',
    'multiple_people': 'This file looks like a shared rota. Remove other people and upload only your rows.',
    'unrecognized_table': 'No shift rows were found. Empty cells are not treated as days off.',
    'unsupported_file': 'Choose a CSV, Excel, PDF or photo file.',
    'signature_mismatch': 'That file does not match its type.',
    'encrypted_file': 'Password-protected files are not accepted.',
    'macro_file': 'Macro-enabled spreadsheets are not accepted.',
    'malformed_file': 'That file could not be read.',
    'file_too_large': 'One of the files is too large.',
    'request_too_large': 'The upload is too large.',
    'too_many_files': 'Too many files were selected.',
    'spreadsheet_too_large': 'That spreadsheet is too large.',
    'pdf_too_large': 'That PDF is too large.',
    'image_too_large': 'That photo is larger than Align can accept.',
    'image_dimensions_unavailable': 'That photo could not be measured.',
    'invalid_upload': 'The upload could not be read.',
}

_IMPORT = re.compile(r'^/api/work/rota/imports/([0-9a-f]{32})$')
_ENTRY = re.compile(r'^/api/work/rota/imports/([0-9a-f]{32})/entries/([0-9a-f]{32})$')
_APPROVE = re.compile(r'^/api/work/rota/imports/([0-9a-f]{32})/approve$')
_UNDO = re.compile(r'^/api/work/rota/imports/([0-9a-f]{32})/undo$')


class RotaError(storage.StorageError):
    pass


def handle_multipart(handler, app, path) -> bool:
    if path != '/api/work/rota/imports':
        return False
    content_type = handler.headers.get('Content-Type', '')
    if 'multipart/form-data' not in content_type.lower():
        return False
    try:
        length = int(handler.headers.get('Content-Length', '-1'))
    except ValueError:
        length = -1
    if length < 0 or length > files.LIMITS['max_total_bytes']:
        handler.close_connection = True
        handler.send_json(413, {'error': _MESSAGES['request_too_large'], 'code': 'request_too_large'})
        return True
    if not _authorized(handler, app):
        _discard(handler, length)
        return True
    body = handler.rfile.read(length)
    if len(body) != length:
        handler.send_json(400, {'error': _MESSAGES['invalid_upload'], 'code': 'invalid_upload'})
        return True
    try:
        uploaded = files.parse_multipart(body, content_type)
        with app.db_connection() as connection:
            _require_work(connection, app)
        extracted = files.extract_files(uploaded)
        with app.db_connection() as connection:
            record = storage.create_import(connection, len(uploaded))
            drafts = []
            notices = []
            warnings = []
            for index, item in enumerate(extracted, start=1):
                if item.get('code'):
                    notices.append(item['code'])
                    warnings.append({'index': index, 'format': item.get('format') or '', 'code': item['code']})
                drafts.extend(item.get('drafts') or [])
            error_code = notices[0] if notices and not drafts else ''
            saved = storage.save_drafts(connection, record['id'], drafts, notices, error_code)
            payload = _import_payload(connection, saved)
            payload['warnings'] = warnings
            if saved['status'] == 'failed':
                payload['error'] = _MESSAGES.get(saved['error_code'], 'This rota could not be read.')
        handler.send_json(201, payload)
    except (files.FileProblem, storage.StorageError, RotaError) as error:
        code = getattr(error, 'code', 'invalid_upload')
        LOG.info('rota upload rejected code=%s', code)
        status = getattr(error, 'status', 400)
        handler.send_json(status, {'error': _MESSAGES.get(code, str(error)), 'code': code})
    except Exception:
        LOG.error('rota upload failed')
        handler.send_json(500, {'error': 'The rota could not be read.', 'code': 'upload_failed'})
    return True


def handle_get(handler, app, connection, path) -> bool:
    if path == '/api/work/rota/capabilities':
        return _guard(handler, app, connection, lambda: (_require_work(connection, app, check_schema=False), handler.send_json(200, _capabilities())))
    match = _IMPORT.fullmatch(path)
    if not match:
        return False
    import_id = match.group(1)

    def send():
        _require_work(connection, app)
        handler.send_json(200, _import_payload(connection, storage.get_import(connection, import_id)))

    return _guard(handler, app, connection, send)


def handle_post(handler, app, connection, path, payload) -> bool:
    if path == '/api/work/rota/imports':
        handler.send_json(415, {'error': 'Upload the rota as files.', 'code': 'multipart_required'})
        return True
    approve_match = _APPROVE.fullmatch(path)
    undo_match = _UNDO.fullmatch(path)
    if not approve_match and not undo_match:
        return False

    def send():
        _require_work(connection, app)
        import_id = (approve_match or undo_match).group(1)
        if approve_match:
            result = work_rota_import.approve(connection, import_id, payload or {})
        else:
            result = work_rota_import.undo(connection, import_id, payload or {})
        result['import'] = _import_payload(connection, storage.get_import(connection, import_id))['import']
        handler.send_json(200, result)

    return _guard(handler, app, connection, send)


def handle_patch(handler, app, connection, path, payload) -> bool:
    match = _ENTRY.fullmatch(path)
    if not match:
        return False

    def send():
        _require_work(connection, app)
        row = storage.update_entry(connection, match.group(1), match.group(2), payload or {})
        current = _import_payload(connection, storage.get_import(connection, match.group(1)))
        handler.send_json(200, {
            'entry': storage.public_entry(row),
            'locations': current['locations'],
            'shift_types': current['shift_types'],
        })

    return _guard(handler, app, connection, send)


def handle_delete(handler, app, connection, path) -> bool:
    match = _IMPORT.fullmatch(path)
    if not match:
        return False

    def send():
        _require_work(connection, app)
        storage.delete_import(connection, match.group(1))
        handler.send_json(200, {'ok': True})

    return _guard(handler, app, connection, send)


def _guard(handler, app, connection, action) -> bool:
    del app
    try:
        action()
    except storage.StorageError as error:
        LOG.info('rota request rejected code=%s', error.code)
        handler.send_json(error.status, {'error': str(error), 'code': error.code})
    except Exception:
        LOG.error('rota request failed')
        try:
            connection.rollback()
        except Exception:
            pass
        handler.send_json(500, {'error': 'The rota could not be saved.', 'code': 'rota_failed'})
    return True


def _authorized(handler, app) -> bool:
    if not getattr(app, 'BETA_MODE', False):
        return True
    row = handler.require_beta_user()
    if not row:
        return False
    return bool(handler.beta_same_origin())


def _require_work(connection, app, check_schema=True):
    import owner_builder
    try:
        layouts = owner_builder.published_layouts(app.DATABASE)
    except Exception as error:
        raise RotaError('Work settings could not be checked.', 'work_opt_in_unavailable', 403) from error
    if any(item.get('id') == 'work' and item.get('optional') for item in layouts):
        opted_in = connection.execute(
            "SELECT 1 FROM settings WHERE setting_key='section_opt_in_work'"
        ).fetchone()
        if not opted_in:
            raise RotaError('Add Work to your account before uploading a rota.', 'work_opt_in_required', 403)
    if check_schema:
        storage.require_schema(connection)


def _capabilities():
    available = rota_ocr_provider.is_available()
    return {**CAPABILITIES, 'image_ocr': available, 'scanned_pdf_ocr': available}


def _import_payload(connection, record):
    entries = [storage.public_entry(row) for row in storage.list_entries(connection, record['id'])]
    choices = storage.catalog(connection)
    return {
        'import': {
            'id': record['id'],
            'status': record['status'],
            'source_file_count': record['source_file_count'],
            'candidate_count': record['candidate_count'],
            'created_count': record['created_count'],
            'skipped_count': record['skipped_count'],
            'error_code': record.get('error_code') or '',
            'notice_codes': record.get('notice_codes') or [],
            'created_at': record.get('created_at') or '',
            'updated_at': record.get('updated_at') or '',
        },
        'entries': entries,
        'locations': [{'id': row['id'], 'name': row['name']} for row in choices['locations']],
        'shift_types': [{'id': row['id'], 'name': row['name']} for row in choices['shift_types']],
        'capabilities': _capabilities(),
    }


def _discard(handler, length: int):
    remaining = length
    while remaining > 0:
        chunk = handler.rfile.read(min(65536, remaining))
        if not chunk:
            break
        remaining -= len(chunk)
