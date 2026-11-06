"""Rota import: file safety, review, approval into shifts, and undo."""
import io
import json
import os
import re
import sqlite3
import struct
import time
import unittest
from unittest import mock
import zipfile
import zlib
from datetime import date, timedelta
from http.client import HTTPConnection
from pathlib import Path

import app
import personal_planner
import planner_api
import rota_file_processor
import rota_ocr_provider
import rota_parser
import work_rota_storage
from test_support import IsolatedAppServer


def png(width, height):
    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))


def heic():
    brand = b'heic'
    return struct.pack('>I', 16) + b'ftyp' + brand + b'\x00\x00\x00\x00'


def simple_pdf(text):
    stream = f'BT ({text}) Tj ET'.encode('latin-1')
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Count 1 /Kids [3 0 R] >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] /Contents 4 0 R >>',
        b'<< /Length %d >>\nstream\n%s\nendstream' % (len(stream), stream),
    ]
    chunks = [b'%PDF-1.4\n']
    offsets = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(sum(len(part) for part in chunks))
        chunks.append(f'{index} 0 obj '.encode() + obj + b' endobj\n')
    xref = sum(len(part) for part in chunks)
    body = ''.join(f'{offset:010d} 00000 n \n' for offset in offsets)
    trailer = f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n{body}trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'
    return b''.join(chunks) + trailer.encode()


def simple_xlsx(rows):
    shared = []

    def sid(value):
        if value not in shared:
            shared.append(value)
        return shared.index(value)

    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    sheet_rows = []
    for row_number, row in enumerate(rows, start=1):
        cells = []
        for column, value in enumerate(row, start=1):
            letter = chr(64 + column)
            cells.append(f'<c r="{letter}{row_number}" t="s"><v>{sid(str(value))}</v></c>')
        sheet_rows.append(f'<row r="{row_number}">{"".join(cells)}</row>')
    shared_xml = f'<sst xmlns="{ns}">{"".join(f"<si><t>{item}</t></si>" for item in shared)}</sst>'
    sheet_xml = f'<worksheet xmlns="{ns}"><sheetData>{"".join(sheet_rows)}</sheetData></worksheet>'
    content_types = (
        '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
        '</Types>'
    )
    workbook = f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Rota" sheetId="1" r:id="rId1"/></sheets></workbook>'
    rels = (
        '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>'
        '</Relationships>'
    )
    root_rels = (
        '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('[Content_Types].xml', content_types)
        archive.writestr('_rels/.rels', root_rels)
        archive.writestr('xl/workbook.xml', workbook)
        archive.writestr('xl/_rels/workbook.xml.rels', rels)
        archive.writestr('xl/sharedStrings.xml', shared_xml)
        archive.writestr('xl/worksheets/sheet1.xml', sheet_xml)
    return buffer.getvalue()


class RotaImportTests(unittest.TestCase):
    tearDown = IsolatedAppServer.tearDown
    request = IsolatedAppServer.request
    json_request = IsolatedAppServer.json_request

    def setUp(self):
        IsolatedAppServer.setUp(self)
        with app.db_connection() as connection:
            connection.execute("INSERT INTO settings(setting_key,setting_value) VALUES('section_opt_in_work','1')")
            self.location_id = connection.execute(
                "INSERT INTO locations(name,address,colour) VALUES('Main Hospital','1 High Street','#365CE6')"
            ).lastrowid
            self.area_id = connection.execute(
                "INSERT INTO shift_types(name,colour) VALUES('Ward','#3B82F6')"
            ).lastrowid
            connection.execute(
                "INSERT INTO alert_rules(title,minutes_before,active) VALUES('Shift reminder',60,1)"
            )
            connection.commit()

    def request_files(self, parts, method='POST', path='/api/work/rota/imports'):
        boundary = 'AlignRotaBoundary'
        chunks = []
        for filename, payload, content_type in parts:
            header = (
                f'--{boundary}\r\n'
                f'Content-Disposition: form-data; name="files"; filename="{filename}"\r\n'
                f'Content-Type: {content_type}\r\n\r\n'
            ).encode()
            chunks.append(header + payload + b'\r\n')
        body = b''.join(chunks) + f'--{boundary}--\r\n'.encode()
        client = HTTPConnection('127.0.0.1', self.server.server_port, timeout=20)
        client.request(method, path, body=body, headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
        response = client.getresponse()
        result = (response.status, response.read())
        client.close()
        return result

    def upload(self, filename, payload, content_type='text/csv', expected=201):
        status, body = self.request_files([(filename, payload, content_type)])
        self.assertEqual(status, expected, body)
        return json.loads(body)

    def csv(self, text):
        return self.upload('rota.csv', text.encode())

    def test_capabilities_are_honest_about_ocr(self):
        payload = self.json_request('GET', '/api/work/rota/capabilities')
        self.assertTrue(payload['csv'] and payload['xlsx'] and payload['pdf_text'])
        self.assertEqual(payload['image_ocr'], rota_ocr_provider.is_available())
        self.assertEqual(payload['scanned_pdf_ocr'], rota_ocr_provider.is_available())
        script = Path('static/work-rota.js').read_text(encoding='utf-8')
        self.assertIn('local OCR runtime', script)
        self.assertIn('Upload my rota', Path('static/app.js').read_text(encoding='utf-8'))
        index = Path('static/index.html').read_text(encoding='utf-8')
        version = re.search(r'/app\.js\?v=([^"\']+)', index)
        self.assertIsNotNone(version)
        self.assertIn(f'/work-rota.js?v={version.group(1)}', index)
        self.assertIn('/work-rota.js?v=${ASSET_VERSION}', Path('static/service-worker.js').read_text(encoding='utf-8'))

    def test_photo_ocr_creates_review_rows_without_retaining_source(self):
        class FakeProvider:
            def extract_text(self, path, media_type):
                self.asserted_path = Path(path)
                if not self.asserted_path.exists():
                    raise AssertionError('temporary OCR input was not available during extraction')
                return '2026-11-09 08:00-16:00 Ward, Ward, Main Hospital'
        fake = FakeProvider()
        with mock.patch.object(rota_ocr_provider, 'get_provider', return_value=fake):
            uploaded = self.upload('my-rota.png', png(400, 200), 'image/png')
        self.assertEqual(uploaded['import']['status'], 'review')
        self.assertEqual(uploaded['entries'][0]['work_date'], '2026-11-09')
        self.assertEqual(uploaded['entries'][0]['start_time'], '08:00')
        self.assertEqual(uploaded['entries'][0]['end_time'], '16:00')
        self.assertFalse(fake.asserted_path.exists())
        self.assertFalse(any(rota_file_processor.temp_root().glob('rota-*')))

    def test_review_can_learn_new_workplace_and_shift_area(self):
        uploaded = self.csv(
            'date,start,end,department,location\n'
            '2026-11-10,08:00,16:00,Clinic,New Hospital\n'
        )
        entry = uploaded['entries'][0]
        self.assertFalse(entry['approvable'])
        saved = self.json_request(
            'PATCH',
            f"/api/work/rota/imports/{uploaded['import']['id']}/entries/{entry['id']}",
            {
                'revision': entry['revision'],
                'create_location': True,
                'new_location_name': 'New Hospital',
                'new_location_address': '2 New Street',
                'create_shift_type': True,
                'new_shift_type_name': 'Clinic',
            },
        )
        self.assertTrue(saved['entry']['approvable'])
        self.assertEqual(saved['entry']['location_text'], 'New Hospital')
        with app.db_connection() as connection:
            location = connection.execute("SELECT id,address FROM locations WHERE name='New Hospital'").fetchone()
            area = connection.execute("SELECT id FROM shift_types WHERE name='Clinic'").fetchone()
            self.assertIsNotNone(location)
            self.assertEqual(location['address'], '2 New Street')
            self.assertIsNotNone(area)
            self.assertTrue(connection.execute(
                'SELECT 1 FROM location_shift_types WHERE location_id=? AND shift_type_id=?',
                (location['id'], area['id']),
            ).fetchone())
        result = self.json_request(
            'POST',
            f"/api/work/rota/imports/{uploaded['import']['id']}/approve",
            {'idempotency_key': 'learn-workplace-01', 'entries': [{'id': entry['id'], 'revision': saved['entry']['revision']}]},
        )
        self.assertEqual(len(result['created']), 1)
        with app.db_connection() as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM shifts WHERE work_date='2026-11-10'"
            ).fetchone()[0], 1)

    def test_work_opt_in_and_bad_signatures(self):
        with app.db_connection() as connection:
            connection.execute("DELETE FROM settings WHERE setting_key='section_opt_in_work'")
            connection.commit()
        status, body = self.request_files([('rota.csv', b'date,start\n', 'text/csv')])
        self.assertEqual(status, 403, body)
        self.assertEqual(json.loads(body)['code'], 'work_opt_in_required')
        with app.db_connection() as connection:
            connection.execute("INSERT INTO settings(setting_key,setting_value) VALUES('section_opt_in_work','1')")
            connection.commit()
        status, body = self.request_files([('photo.jpg', b'%PDF-1.4 not a jpeg', 'image/jpeg')])
        self.assertEqual(status, 400, body)
        self.assertEqual(json.loads(body)['code'], 'signature_mismatch')
        status, body = self.request_files([('rota.csv.exe', b'date,start\n', 'text/csv')])
        self.assertEqual(status, 400, body)
        self.assertEqual(json.loads(body)['code'], 'unsupported_file')
        status, body = self.request_files([('huge.png', png(9001, 10), 'image/png')])
        self.assertEqual(status, 400, body)
        self.assertEqual(json.loads(body)['code'], 'image_too_large')
        status, body = self.request_files([('locked.pdf', b'%PDF-1.4\n1 0 obj << /Encrypt 2 0 R >> endobj\n', 'application/pdf')])
        self.assertEqual(status, 400, body)
        self.assertEqual(json.loads(body)['code'], 'encrypted_file')
        macro = io.BytesIO()
        with zipfile.ZipFile(macro, 'w') as archive:
            archive.writestr('xl/vbaProject.bin', b'not executed')
            archive.writestr('xl/worksheets/sheet1.xml', '<worksheet/>')
        status, body = self.request_files([('book.xlsx', macro.getvalue(), 'application/vnd.ms-excel')])
        self.assertEqual(status, 400, body)
        self.assertEqual(json.loads(body)['code'], 'macro_file')

    def test_limits_and_abandoned_temp_files(self):
        original = dict(rota_file_processor.LIMITS)
        try:
            rota_file_processor.LIMITS['max_total_bytes'] = 40
            status, body = self.request_files([('rota.csv', b'a' * 80, 'text/csv')])
            self.assertEqual(status, 413, body)
            rota_file_processor.LIMITS['max_total_bytes'] = original['max_total_bytes']
            rota_file_processor.LIMITS['max_files'] = 1
            status, body = self.request_files([
                ('a.csv', b'date,start,end\n2026-11-03,08:00,16:00\n', 'text/csv'),
                ('b.csv', b'date,start,end\n2026-11-04,08:00,16:00\n', 'text/csv'),
            ])
            self.assertEqual(status, 400, body)
            self.assertEqual(json.loads(body)['code'], 'too_many_files')
        finally:
            rota_file_processor.LIMITS.clear()
            rota_file_processor.LIMITS.update(original)
        root = rota_file_processor.temp_root()
        stale = root / 'rota-stale'
        fresh = root / 'rota-fresh'
        stale.write_bytes(b'stale')
        fresh.write_bytes(b'fresh')
        old = time.time() - rota_file_processor.LIMITS['abandoned_seconds'] - 10
        os.utime(stale, (old, old))
        self.assertGreaterEqual(rota_file_processor.cleanup_abandoned(), 1)
        self.assertFalse(stale.exists())
        self.assertTrue(fresh.exists())
        fresh.unlink()

    def test_csv_review_approval_visibility_and_undo(self):
        text = (
            'date,start,end,label,department,location\n'
            '2026-11-03,08:00,16:00,Ward AM,Ward,Main Hospital\n'
            '2026-11-04,22:00,06:00,Night,Ward,Main Hospital\n'
            '\n'
            '03/04/2026,09:00,17:00,Ambiguous,Ward,Main Hospital\n'
            '2026-11-05,, ,Day off,,\n'
            '2026-11-06,,,annual leave,,\n'
            '2026-11-07,,,sickness,,\n'
            '2026-11-08,,,,,\n'
        )
        # The day-off row above is not a kind column. Build an explicit kind file instead.
        text = (
            'date,start,end,label,department,location,kind\n'
            '2026-11-03,08:00,16:00,Ward AM,Ward,Main Hospital,shift\n'
            '2026-11-04,22:00,06:00,Night,Ward,Main Hospital,shift\n'
            '\n'
            '03/04/2026,09:00,17:00,Ambiguous,Ward,Main Hospital,shift\n'
            '2026-11-05,,,,Day off,,day off\n'
            '2026-11-06,,,,annual leave,,leave\n'
            '2026-11-07,,,,sickness,,sickness\n'
            '2026-11-08,,,,,,\n'
        )
        uploaded = self.csv(text)
        by_date = {entry['work_date'] or entry['source_date_text']: entry for entry in uploaded['entries']}
        self.assertEqual(uploaded['import']['status'], 'review')
        self.assertTrue(by_date['2026-11-03']['approvable'])
        self.assertTrue(by_date['2026-11-03']['preselected'])
        self.assertEqual(by_date['2026-11-03']['confidence_band'], 'high')
        self.assertEqual(by_date['2026-11-04']['end_time'], '06:00')
        self.assertFalse(by_date['03/04/2026']['approvable'])
        self.assertEqual(by_date['03/04/2026']['ambiguity'], 'date')
        self.assertEqual(by_date['2026-11-05']['entry_kind'], 'day_off')
        self.assertEqual(by_date['2026-11-06']['entry_kind'], 'leave')
        self.assertEqual(by_date['2026-11-07']['entry_kind'], 'sickness')
        self.assertEqual(by_date['2026-11-08']['entry_kind'], 'unknown')
        self.assertNotIn('03/04/2026', [entry['work_date'] for entry in uploaded['entries'] if entry['work_date']])
        import_id = uploaded['import']['id']
        day = by_date['2026-11-03']
        night = by_date['2026-11-04']
        off = by_date['2026-11-05']
        leave = by_date['2026-11-06']
        ambiguous = by_date['03/04/2026']
        status, _, body = self.request('POST', f'/api/work/rota/imports/{import_id}/approve', {
            'idempotency_key': 'approve-once',
            'entries': [{'id': ambiguous['id'], 'revision': ambiguous['revision']}],
        })
        self.assertEqual(status, 200, body)
        blocked = json.loads(body)
        self.assertTrue(blocked['conflicts'])
        with app.db_connection() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM shifts').fetchone()[0], 0)
        first = self.json_request('POST', f'/api/work/rota/imports/{import_id}/approve', {
            'idempotency_key': 'approve-selected',
            'entries': [
                {'id': day['id'], 'revision': day['revision']},
                {'id': off['id'], 'revision': off['revision']},
                {'id': leave['id'], 'revision': leave['revision']},
            ],
        }, expected=200)
        self.assertEqual(len(first['created']), 1)
        self.assertEqual(len(first['leave']), 1)
        self.assertEqual(len(first['acknowledged']), 1)
        repeated = self.json_request('POST', f'/api/work/rota/imports/{import_id}/approve', {
            'idempotency_key': 'approve-selected',
            'entries': [{'id': night['id'], 'revision': night['revision']}],
        }, expected=200)
        self.assertEqual(repeated['created'], first['created'])
        with app.db_connection() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM shifts').fetchone()[0], 1)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM alerts').fetchone()[0], 1)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM organiser_events').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM annual_leave').fetchone()[0], 1)
            shift = dict(connection.execute('SELECT * FROM shifts').fetchone())
            self.assertEqual(shift['hours'], 8)
            self.assertEqual(shift['source_import_entry_id'], day['id'])
            self.assertEqual(planner_api._week(connection, '2026-11-03')['shifts'][0]['id'], shift['id'])
            titles = [event['title'] for event in personal_planner.events(connection, date(2026, 11, 3))]
            self.assertIn('Main Hospital – Ward', titles)
        second = self.json_request('POST', f'/api/work/rota/imports/{import_id}/approve', {
            'idempotency_key': 'approve-night',
            'entries': [{'id': night['id'], 'revision': night['revision']}],
        }, expected=200)
        self.assertEqual(len(second['created']), 1)
        with app.db_connection() as connection:
            night_row = dict(connection.execute(
                "SELECT * FROM shifts WHERE work_date='2026-11-04'"
            ).fetchone())
            self.assertEqual(night_row['hours'], 8)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM alerts').fetchone()[0], 2)
            connection.execute("UPDATE shifts SET start_time='21:00' WHERE id=?", (night_row['id'],))
            connection.commit()
        undone = self.json_request('POST', f'/api/work/rota/imports/{import_id}/undo', {}, expected=200)
        self.assertTrue(any(item['entry_id'] == night['id'] for item in undone['conflicts']))
        with app.db_connection() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM shifts').fetchone()[0], 2)
            connection.execute("UPDATE shifts SET start_time='22:00' WHERE id=?", (night_row['id'],))
            connection.commit()
        undone = self.json_request('POST', f'/api/work/rota/imports/{import_id}/undo', {}, expected=200)
        self.assertGreaterEqual(len(undone['removed']), 1)
        with app.db_connection() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM shifts').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM alerts').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM organiser_events').fetchone()[0], 0)

    def test_duplicate_overlap_revision_and_account_isolation(self):
        uploaded = self.csv(
            'date,start,end,department,location\n'
            '2026-12-01,08:00,16:00,Ward,Main Hospital\n'
            '2026-12-02,08:00,16:00,Ward,Main Hospital\n'
        )
        first, second = uploaded['entries']
        self.json_request('POST', f"/api/work/rota/imports/{uploaded['import']['id']}/approve", {
            'idempotency_key': 'approve-one-day',
            'entries': [{'id': first['id'], 'revision': first['revision']}],
        }, expected=200)
        with app.db_connection() as connection:
            connection.execute(
                "INSERT INTO shifts(work_date,location_id,shift_type_id,location_name,shift_type_name,colour,start_time,end_time,break_minutes,hours,notes) "
                "VALUES('2026-12-02',?,?, 'Main Hospital','Ward','#365CE6','10:00','14:00',0,4,'')",
                (self.location_id, self.area_id),
            )
            connection.commit()
        overlap = self.json_request('POST', f"/api/work/rota/imports/{uploaded['import']['id']}/approve", {
            'idempotency_key': 'approve-overlap',
            'entries': [{'id': second['id'], 'revision': second['revision']}],
        }, expected=200)
        self.assertTrue(overlap['conflicts'])
        again = self.csv(
            'date,start,end,department,location\n2026-12-01,08:00,16:00,Ward,Main Hospital\n'
        )
        with app.db_connection() as connection:
            existing_id = connection.execute(
                "SELECT id FROM shifts WHERE work_date='2026-12-01'"
            ).fetchone()[0]
        self.assertEqual(again['entries'][0]['duplicate_shift_id'], existing_id)
        self.assertFalse(again['entries'][0]['approvable'])
        status, _, body = self.request('PATCH', f"/api/work/rota/imports/{again['import']['id']}/entries/{again['entries'][0]['id']}", {
            'revision': again['entries'][0]['revision'] + 5,
            'work_date': '2026-12-03',
        })
        self.assertEqual(status, 409, body)
        corrected = self.json_request('PATCH', f"/api/work/rota/imports/{uploaded['import']['id']}/entries/{second['id']}", {
            'revision': second['revision'],
            'start_time': '15:00',
            'end_time': '20:00',
        })
        self.assertTrue(corrected['entry']['approvable'])
        other = Path(self.temp.name) / 'other.sqlite3'
        app.initialise_database_at(other)
        with sqlite3.connect(other) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute('PRAGMA foreign_keys=ON')
            with self.assertRaises(work_rota_storage.StorageError) as raised:
                work_rota_storage.get_import(connection, uploaded['import']['id'])
            self.assertEqual(raised.exception.status, 404)

    def test_shared_names_are_not_stored_and_native_files_extract(self):
        secret = 'Colleague Secret Name'
        uploaded = self.csv(
            'name,date,start,end,location\n'
            f'Alex,2026-11-03,08:00,16:00,Main Hospital\n'
            f'{secret},2026-11-04,08:00,16:00,Main Hospital\n'
        )
        self.assertEqual(uploaded['import']['status'], 'failed')
        self.assertEqual(uploaded['import']['error_code'], 'multiple_people')
        self.assertEqual(uploaded['entries'], [])
        with app.db_connection() as connection:
            raw = '\n'.join(
                str(tuple(row)) for row in connection.execute('SELECT * FROM work_rota_imports').fetchall()
            )
            self.assertNotIn(secret, raw)
        pdf = self.upload('rota.pdf', simple_pdf('2026-11-03 08:00-16:00 Ward at Main Hospital'), 'application/pdf')
        self.assertEqual(pdf['entries'][0]['work_date'], '2026-11-03')
        self.assertEqual(pdf['entries'][0]['location_text'], 'Main Hospital')
        sheet = simple_xlsx([
            ['date', 'start', 'end', 'department', 'location'],
            ['25/03/2026', '08:00', '16:00', 'Ward', 'Main Hospital'],
        ])
        xlsx = self.upload('rota.xlsx', sheet, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.assertEqual(xlsx['entries'][0]['work_date'], '2026-03-25')
        self.assertTrue(xlsx['entries'][0]['approvable'])
        class BrokenProvider:
            def extract_text(self, path, media_type):
                raise rota_ocr_provider.OcrError('invalid test image')
        with mock.patch.object(rota_ocr_provider, 'get_provider', return_value=BrokenProvider()):
            photo = self.upload('rota.heic', heic(), 'image/heic')
        self.assertEqual(photo['import']['status'], 'failed')
        self.assertEqual(photo['import']['error_code'], 'ocr_failed')
        self.assertEqual(photo['capabilities']['image_ocr'], rota_ocr_provider.is_available())
        self.assertEqual(rota_file_processor.cleanup_abandoned(max_age=-1) >= 0, True)
        self.assertFalse(any(rota_file_processor.temp_root().glob('rota-*')))

    def test_dates_dst_and_schema_parity(self):
        self.assertEqual(rota_parser.parse_date('25/03/2026')[0], '2026-03-25')
        self.assertTrue(rota_parser.parse_date('03/04/2026')[1])
        self.assertEqual(rota_parser.parse_date('03/25/2026')[0], '2026-03-25')
        self.assertEqual(rota_parser.parse_date('9 Nov 2026')[0], '2026-11-09')
        ocr_row = rota_parser.interpret_pdf_text('Mon 9 Nov 2026 08:00 16:00 Ward at Main Hospital')[0]
        self.assertEqual(ocr_row['work_date'], '2026-11-09')
        self.assertEqual(ocr_row['start_time'], '08:00')
        self.assertEqual(ocr_row['end_time'], '16:00')
        self.assertEqual(
            rota_parser.excel_date((date(2026, 11, 3) - date(1899, 12, 30)).days),
            '2026-11-03',
        )
        self.assertEqual(rota_parser.excel_time(8 / 24), '08:00')
        gap = rota_parser.local_clock_status('2026-03-29', '01:30')
        fold = rota_parser.local_clock_status('2026-10-25', '01:30')
        self.assertEqual(gap, 'time_gap')
        self.assertEqual(fold, 'time_fold')
        drafted = rota_parser.interpret_table([
            ['date', 'start', 'end', 'department', 'location'],
            ['2026-03-29', '01:30', '09:30', 'Ward', 'Main Hospital'],
        ])[0]
        self.assertEqual(drafted['ambiguity'], 'time_gap')
        self.assertEqual(rota_ocr_provider.LocalTesseractProvider.name, 'local-tesseract')
        root = Path('migrations')
        sqlite_sql = (root / '157_work_rota_import.sql').read_text(encoding='utf-8')
        postgres_sql = (root / 'postgres' / '157_work_rota_import.sql').read_text(encoding='utf-8')
        fresh = (root / 'postgres' / 'fresh_v3_schema.sql').read_text(encoding='utf-8')
        readme = (root / 'postgres' / 'README.md').read_text(encoding='utf-8')
        for text in (sqlite_sql, postgres_sql, fresh, Path('schema_v3.sqlite.sql').read_text(encoding='utf-8')):
            self.assertIn('work_rota_imports', text)
            self.assertIn('work_rota_entries', text)
        self.assertIn('source_import_entry_id', fresh)
        self.assertIn('source_import_entry_id', postgres_sql)
        self.assertIn('157_work_rota_import', readme)
        self.assertIn('157_work_rota_import', (root / 'postgres' / 'HOSTED_SCHEMA_PREFLIGHT.sql').read_text(encoding='utf-8'))
        with sqlite3.connect(app.DATABASE) as connection:
            connection.execute('PRAGMA foreign_keys=OFF')
            connection.execute('DROP INDEX IF EXISTS idx_shifts_source_import_entry')
            connection.execute('ALTER TABLE shifts DROP COLUMN source_import_entry_id')
            connection.execute('DROP TABLE work_rota_approvals')
            connection.execute('DROP TABLE work_rota_entries')
            connection.execute('DROP TABLE work_rota_imports')
            connection.execute("DELETE FROM schema_migrations WHERE migration_id='157_work_rota_import'")
            connection.commit()
        import migration_runner
        migration_runner.ensure_work_rota_schema(app.DATABASE)
        with sqlite3.connect(app.DATABASE) as connection:
            columns = {row[1] for row in connection.execute('PRAGMA table_info(shifts)')}
            self.assertIn('source_import_entry_id', columns)
            self.assertTrue(connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name='work_rota_imports'"
            ).fetchone())


if __name__ == '__main__':
    import unittest
    unittest.main()
