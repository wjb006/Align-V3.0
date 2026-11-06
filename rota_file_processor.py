"""Allowlisted rota intake, signature checks and temporary-file cleanup.

Original bytes stay in a private temp directory only while a file is read,
then they are deleted. Images and scanned PDFs use the optional local Tesseract runtime.
"""
from __future__ import annotations

import os
import re
import secrets
import stat
import tempfile
import zipfile
import zlib
from pathlib import Path
from xml.etree import ElementTree

import rota_ocr_provider
import rota_parser

LIMITS = {
    'max_files': 8,
    'max_file_bytes': 8 * 1024 * 1024,
    'max_total_bytes': 20 * 1024 * 1024,
    'max_pdf_pages': 20,
    'max_rows': 400,
    'max_columns': 32,
    'max_image_edge': 8000,
    'max_entries': 400,
    'max_zip_member': 5 * 1024 * 1024,
    'max_zip_total': 30 * 1024 * 1024,
    'max_pdf_stream': 2 * 1024 * 1024,
    'max_pdf_text': 1 * 1024 * 1024,
    'abandoned_seconds': 6 * 60 * 60,
}

ALLOWED = {
    'csv': 'text/csv',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'pdf': 'application/pdf',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'png': 'image/png',
    'heic': 'image/heic',
    'heif': 'image/heif',
}
_NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
_TEMP_PREFIX = 'rota-'


class FileProblem(ValueError):
    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


def temp_root() -> Path:
    root = Path(tempfile.gettempdir()) / 'align-rota-private'
    root.mkdir(mode=0o700, exist_ok=True)
    try:
        os.chmod(root, 0o700)
    except OSError:
        pass
    return root


def cleanup_abandoned(now=None, max_age=None):
    """Delete leftover temp files after a crash. Active files are left alone."""
    import time
    cutoff = (now if now is not None else time.time()) - (LIMITS['abandoned_seconds'] if max_age is None else max_age)
    removed = 0
    root = temp_root()
    for path in root.iterdir():
        try:
            if not path.is_file() or not path.name.startswith(_TEMP_PREFIX):
                continue
            if path.stat().st_mtime <= cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed


def _write_temp(payload: bytes) -> Path:
    path = temp_root() / f'{_TEMP_PREFIX}{secrets.token_hex(16)}'
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(fd, payload)
    finally:
        os.close(fd)
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return path


def _extension(filename: str) -> str:
    base = str(filename or '').replace('\\', '/').split('/')[-1]
    if not base or base.startswith('.') or '/' in base or '\\' in base:
        raise FileProblem('Choose a CSV, Excel, PDF or photo file.', 'unsupported_file')
    suffix = Path(base).suffix.lower().lstrip('.')
    if suffix not in ALLOWED or base.count('.') != 1:
        raise FileProblem('Choose a CSV, Excel, PDF or photo file.', 'unsupported_file')
    return suffix


def _png_size(payload: bytes):
    if len(payload) < 24 or payload[12:16] != b'IHDR':
        raise FileProblem('This PNG could not be read.', 'malformed_file')
    width = int.from_bytes(payload[16:20], 'big')
    height = int.from_bytes(payload[20:24], 'big')
    return width, height


def _jpeg_size(payload: bytes):
    if len(payload) < 4 or payload[:3] != b'\xff\xd8\xff':
        raise FileProblem('This JPEG could not be read.', 'malformed_file')
    index = 2
    while index + 9 < len(payload):
        if payload[index] != 0xFF:
            index += 1
            continue
        marker = payload[index + 1]
        if marker in {0xC0, 0xC1, 0xC2}:
            height = int.from_bytes(payload[index + 5:index + 7], 'big')
            width = int.from_bytes(payload[index + 7:index + 9], 'big')
            return width, height
        if marker == 0xD8 or marker == 0xD9:
            index += 2
            continue
        if index + 4 > len(payload):
            break
        length = int.from_bytes(payload[index + 2:index + 4], 'big')
        if length < 2:
            break
        index += 2 + length
    raise FileProblem('This JPEG could not be measured.', 'image_dimensions_unavailable')


def _check_image(payload: bytes, extension: str):
    if extension in {'jpg', 'jpeg'}:
        if payload[:3] != b'\xff\xd8\xff':
            raise FileProblem('This file does not match its JPEG type.', 'signature_mismatch')
        width, height = _jpeg_size(payload)
    elif extension == 'png':
        if payload[:8] != b'\x89PNG\r\n\x1a\n':
            raise FileProblem('This file does not match its PNG type.', 'signature_mismatch')
        width, height = _png_size(payload)
    else:
        if len(payload) < 12 or payload[4:8] != b'ftyp' or payload[8:12] not in {b'heic', b'heix', b'hevc', b'heif', b'mif1', b'msf1'}:
            raise FileProblem('This file does not match its HEIC type.', 'signature_mismatch')
        return
    if width < 1 or height < 1 or width > LIMITS['max_image_edge'] or height > LIMITS['max_image_edge']:
        raise FileProblem('This photo is larger than Align can accept.', 'image_too_large')


def _signature(payload: bytes, extension: str):
    if extension == 'pdf':
        if not payload.startswith(b'%PDF-'):
            raise FileProblem('This file does not match its PDF type.', 'signature_mismatch')
        if b'/Encrypt' in payload[:200000]:
            raise FileProblem('Password-protected PDFs are not accepted.', 'encrypted_file')
        return
    if extension == 'xlsx':
        if not payload.startswith(b'PK\x03\x04'):
            raise FileProblem('This file does not match its Excel type.', 'signature_mismatch')
        return
    if extension == 'csv':
        if b'\x00' in payload[:8192]:
            raise FileProblem('This CSV could not be read as text.', 'malformed_file')
        try:
            payload.decode('utf-8-sig')
        except UnicodeError as error:
            raise FileProblem('This CSV must be UTF-8 text.', 'malformed_file') from error
        return
    _check_image(payload, extension)


def parse_multipart(body: bytes, content_type: str):
    match = re.search(r'boundary="?([A-Za-z0-9\'()+_,\-./:=?]{1,70})"?', content_type or '', re.I)
    if not match:
        raise FileProblem('The upload was not a valid file form.', 'invalid_upload')
    boundary = match.group(1).encode('ascii')
    marker = b'--' + boundary
    if len(body) > LIMITS['max_total_bytes']:
        raise FileProblem('The upload is too large.', 'request_too_large')
    files = []
    for part in body.split(marker)[1:]:
        if part.startswith(b'--') or part in {b'', b'\r\n', b'--\r\n'}:
            continue
        if part.startswith(b'\r\n'):
            part = part[2:]
        if part.endswith(b'\r\n'):
            part = part[:-2]
        if part.endswith(b'--'):
            part = part[:-2]
            if part.endswith(b'\r\n'):
                part = part[:-2]
        split = part.split(b'\r\n\r\n', 1)
        if len(split) != 2:
            raise FileProblem('The upload was not a valid file form.', 'invalid_upload')
        header_blob, data = split
        if len(header_blob) > 8192:
            raise FileProblem('The upload was not a valid file form.', 'invalid_upload')
        header = header_blob.decode('latin-1', errors='replace')
        if 'content-disposition' not in header.lower() or 'filename=' not in header.lower():
            continue
        filename = ''
        quoted = re.search(r'filename="([^"]*)"', header, re.I)
        plain = re.search(r'filename=([^;\r\n]+)', header, re.I)
        if quoted:
            filename = quoted.group(1)
        elif plain:
            filename = plain.group(1).strip().strip('"')
        extension = _extension(filename)
        if len(data) > LIMITS['max_file_bytes']:
            raise FileProblem('One of the files is too large.', 'file_too_large')
        files.append({'extension': extension, 'data': data, 'media_type': ALLOWED[extension]})
    if not files:
        raise FileProblem('Choose at least one file.', 'invalid_upload')
    if len(files) > LIMITS['max_files']:
        raise FileProblem(f'Choose up to {LIMITS["max_files"]} files.', 'too_many_files')
    if sum(len(item['data']) for item in files) > LIMITS['max_total_bytes']:
        raise FileProblem('The upload is too large.', 'request_too_large')
    return files


def _xlsx_rows(payload: bytes):
    try:
        archive = zipfile.ZipFile(__import__('io').BytesIO(payload))
    except zipfile.BadZipFile as error:
        raise FileProblem('This Excel file could not be read.', 'malformed_file') from error
    names = set(archive.namelist())
    if any(name.endswith('vbaProject.bin') or 'macro' in name.casefold() for name in names):
        raise FileProblem('Macro-enabled spreadsheets are not accepted.', 'macro_file')
    if any(name.casefold().startswith('encryptedpackage') or 'encryptioninfo' in name.casefold() for name in names):
        raise FileProblem('Password-protected spreadsheets are not accepted.', 'encrypted_file')
    total = 0
    for info in archive.infolist():
        if info.file_size > LIMITS['max_zip_member']:
            raise FileProblem('This Excel file is too large to read.', 'spreadsheet_too_large')
        total += info.file_size
        if total > LIMITS['max_zip_total']:
            raise FileProblem('This Excel file is too large to read.', 'spreadsheet_too_large')
    shared = []
    if 'xl/sharedStrings.xml' in names:
        root = ElementTree.fromstring(archive.read('xl/sharedStrings.xml'))
        for item in root.findall(f'{_NS}si'):
            shared.append(''.join(node.text or '' for node in item.iter(f'{_NS}t')))
    sheet_name = 'xl/worksheets/sheet1.xml'
    if sheet_name not in names:
        sheets = sorted(name for name in names if name.startswith('xl/worksheets/sheet'))
        if not sheets:
            raise FileProblem('This Excel file has no sheet.', 'malformed_file')
        sheet_name = sheets[0]
    root = ElementTree.fromstring(archive.read(sheet_name))
    rows = []
    for row in root.findall(f'.//{_NS}sheetData/{_NS}row'):
        if len(rows) >= LIMITS['max_rows']:
            raise FileProblem('This spreadsheet has too many rows.', 'spreadsheet_too_large')
        cells = []
        for cell in row.findall(f'{_NS}c'):
            if len(cells) >= LIMITS['max_columns']:
                raise FileProblem('This spreadsheet has too many columns.', 'spreadsheet_too_large')
            ref = cell.attrib.get('r', '')
            column = 0
            for char in ref:
                if char.isalpha():
                    column = column * 26 + (ord(char.upper()) - 64)
            while len(cells) < max(column - 1, len(cells)):
                cells.append('')
            kind = cell.attrib.get('t', '')
            value_node = cell.find(f'{_NS}v')
            inline = cell.find(f'{_NS}is/{_NS}t')
            if cell.find(f'{_NS}f') is not None and value_node is None and inline is None:
                text = ''
            elif kind == 's' and value_node is not None and value_node.text:
                index = int(value_node.text)
                text = shared[index] if 0 <= index < len(shared) else ''
            elif inline is not None:
                text = inline.text or ''
            else:
                text = value_node.text if value_node is not None and value_node.text else ''
            if column:
                while len(cells) < column:
                    cells.append('')
                cells[column - 1] = text
            else:
                cells.append(text)
        rows.append(cells[:LIMITS['max_columns']])
    return _coerce_sheet(rows)


def _coerce_sheet(rows):
    if not rows:
        return rows
    mapping = {}
    for index, header in enumerate(rows[0]):
        key = rota_parser._header_key(header)
        if key in rota_parser._DATE_HEADERS:
            mapping[index] = 'date'
        elif key in rota_parser._START_HEADERS | rota_parser._END_HEADERS:
            mapping[index] = 'time'
    coerced = [rows[0]]
    for cells in rows[1:]:
        copy = list(cells)
        for index, kind in mapping.items():
            if index >= len(copy) or copy[index] in ('', None):
                continue
            if kind == 'date':
                iso = rota_parser.excel_date(copy[index])
                if iso:
                    copy[index] = iso
            elif kind == 'time':
                clock = rota_parser.excel_time(copy[index])
                if clock and not rota_parser.parse_clock(copy[index]):
                    copy[index] = clock
        coerced.append(copy)
    return coerced


def _pdf_text(payload: bytes) -> str:
    if re.search(br'/Type\s*/Page(?!s)', payload) is None and b'stream' not in payload:
        raise FileProblem('This PDF could not be read.', 'malformed_file')
    pages = len(re.findall(br'/Type\s*/Page(?!s)', payload))
    if pages > LIMITS['max_pdf_pages']:
        raise FileProblem('This PDF has too many pages.', 'pdf_too_large')
    chunks = []
    total = 0
    for match in re.finditer(br'stream\r?\n(.*?)\r?\n?endstream', payload, re.S):
        raw = match.group(1)
        window = payload[max(0, match.start() - 300):match.start()]
        if b'FlateDecode' in window:
            try:
                raw = zlib.decompress(raw, wbits=15, bufsize=LIMITS['max_pdf_stream'])
            except zlib.error:
                continue
            if len(raw) > LIMITS['max_pdf_stream']:
                raise FileProblem('This PDF is too large to read.', 'pdf_too_large')
        chunks.append(raw)
        total += len(raw)
        if total > LIMITS['max_pdf_text']:
            raise FileProblem('This PDF is too large to read.', 'pdf_too_large')
        if len(chunks) > 40:
            break
    pieces = []
    for chunk in chunks:
        text = chunk.decode('latin-1', errors='ignore')
        for literal in re.findall(r'\((?:\\.|[^\\)]){0,400}\)', text):
            pieces.append(_pdf_unescape(literal[1:-1]))
    extracted = '\n'.join(piece for piece in pieces if piece.strip())
    if len(re.findall(r'[A-Za-z0-9]', extracted)) < 8:
        raise FileProblem('This PDF has no readable text. Scanned PDFs need image reading, which is not switched on.', 'ocr_unavailable')
    return extracted[:LIMITS['max_pdf_text']]


def _pdf_unescape(value: str) -> str:
    output = []
    index = 0
    while index < len(value):
        char = value[index]
        if char != '\\':
            output.append(char)
            index += 1
            continue
        index += 1
        if index >= len(value):
            break
        escaped = value[index]
        output.append({'n': '\n', 'r': '\r', 't': '\t', '(': '(', ')': ')', '\\': '\\'}.get(escaped, escaped))
        index += 1
    return ''.join(output)


def extract_files(files):
    """Validate every file, extract supported text, and always delete temp copies."""
    cleanup_abandoned()
    paths = []
    results = []
    try:
        for item in files:
            _signature(item['data'], item['extension'])
            path = _write_temp(item['data'])
            paths.append(path)
            results.append(_extract_one(path, item))
        return results
    finally:
        for path in paths:
            try:
                path.unlink()
            except OSError:
                pass


def _ocr_drafts(path: Path, media_type: str):
    text = rota_ocr_provider.get_provider().extract_text(path, media_type)
    return rota_parser.interpret_pdf_text(text)


def _extract_one(path: Path, item):
    extension = item['extension']
    payload = None
    try:
        if extension in {'jpg', 'jpeg', 'png', 'heic', 'heif'}:
            drafts = _ocr_drafts(path, item['media_type'])
        else:
            payload = path.read_bytes()
            if extension == 'csv':
                drafts = rota_parser.interpret_table(_csv_rows(payload))
            elif extension == 'xlsx':
                drafts = rota_parser.interpret_table(_xlsx_rows(payload))
            else:
                drafts = _ocr_drafts(path, item['media_type'])
    except rota_ocr_provider.OcrUnavailable:
        return {'format': extension, 'code': 'ocr_unavailable', 'drafts': []}
    except rota_parser.ParseProblem as error:
        return {'format': extension, 'code': error.code, 'message': str(error), 'drafts': []}
    if len(drafts) > LIMITS['max_rows']:
        raise FileProblem('This file has too many rows.', 'spreadsheet_too_large')
    return {'format': extension, 'code': '', 'drafts': drafts}


def _csv_rows(payload: bytes):
    import csv
    import io
    text = payload.decode('utf-8-sig')
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=',;\t')
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    rows = []
    for cells in reader:
        if len(rows) >= LIMITS['max_rows']:
            raise FileProblem('This spreadsheet has too many rows.', 'spreadsheet_too_large')
        if len(cells) > LIMITS['max_columns']:
            raise FileProblem('This spreadsheet has too many columns.', 'spreadsheet_too_large')
        rows.append([rota_parser.clean_text(cell, 200) for cell in cells])
    return rows
