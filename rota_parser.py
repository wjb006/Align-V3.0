"""Normalize extracted rota rows into review entries.

Dates that can be read as more than one calendar day stay unresolved.
Clock times follow the planner's Europe/London local-time convention.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('Europe/London')
EXCEL_EPOCH = date(1899, 12, 30)
HIGH_CONFIDENCE = 0.85
MEDIUM_CONFIDENCE = 0.5
KINDS = ('shift', 'day_off', 'leave', 'sickness', 'unknown')

_NAME_HEADERS = {'name', 'employee', 'staff', 'person', 'colleague', 'worker'}
_DATE_HEADERS = {'date', 'workdate', 'day', 'shiftdate', 'ondate'}
_START_HEADERS = {'start', 'starttime', 'from', 'begin', 'begins'}
_END_HEADERS = {'end', 'endtime', 'to', 'finish', 'until'}
_LABEL_HEADERS = {'shift', 'label', 'duty', 'role', 'pattern'}
_DEPARTMENT_HEADERS = {'department', 'area', 'ward', 'unit', 'team'}
_LOCATION_HEADERS = {'location', 'site', 'workplace', 'hospital', 'place'}
_KIND_HEADERS = {'kind', 'type', 'status', 'entry', 'category'}

_SICKNESS = {'sick', 'sickness', 'ill', 'illness'}
_LEAVE = {'annual leave', 'leave', 'al', 'holiday', 'vacation', 'annualleave'}
_DAY_OFF = {'day off', 'dayoff', 'off', 'rest', 'rest day', 'off duty', 'do', 'day-off'}


class ParseProblem(ValueError):
    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


def clean_text(value, limit: int) -> str:
    text = ''.join(ch for ch in str(value or '') if ch == '\t' or ord(ch) >= 32)
    return re.sub(r'\s+', ' ', text).strip()[:limit]


def _header_key(value) -> str:
    return re.sub(r'[^a-z0-9]', '', str(value or '').casefold())


def _kind_token(value) -> str:
    token = clean_text(value, 40).casefold()
    if token in _SICKNESS:
        return 'sickness'
    if token in _LEAVE:
        return 'leave'
    if token in _DAY_OFF:
        return 'day_off'
    if token in {'shift', 'work', 'working', 'duty'}:
        return 'shift'
    return ''


def parse_clock(value) -> str | None:
    text = clean_text(value, 16).lower().replace('.', ':')
    if not text:
        return None
    match = re.fullmatch(r'(\d{1,2}):(\d{2})', text) or re.fullmatch(r'(\d{2})(\d{2})', text)
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return f'{hour:02d}:{minute:02d}'


def excel_date(number) -> str | None:
    """Convert an Excel serial into an ISO date. Values before 2000 are refused."""
    try:
        serial = float(number)
    except (TypeError, ValueError):
        return None
    if serial < 20000 or serial > 80000:
        return None
    resolved = EXCEL_EPOCH + timedelta(days=int(serial))
    if not 2000 <= resolved.year <= 2100:
        return None
    return resolved.isoformat()


def excel_time(number) -> str | None:
    try:
        fraction = float(number)
    except (TypeError, ValueError):
        return None
    if fraction < 0:
        return None
    fraction = fraction % 1
    minutes = int(round(fraction * 24 * 60))
    if minutes == 24 * 60:
        minutes = 0
    if not 0 <= minutes < 24 * 60:
        return None
    return f'{minutes // 60:02d}:{minutes % 60:02d}'


def parse_date(value):
    """Return (iso_date or None, ambiguous flag, original text)."""
    text = clean_text(value, 40)
    if not text:
        return None, False, ''
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', text):
        try:
            return date.fromisoformat(text).isoformat(), False, text
        except ValueError:
            return None, True, text
    for pattern in ('%d %b %Y', '%d %B %Y', '%b %d %Y', '%B %d %Y', '%b %d, %Y', '%B %d, %Y'):
        try:
            return datetime.strptime(text, pattern).date().isoformat(), False, text
        except ValueError:
            continue
    match = re.fullmatch(r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})', text)
    if not match:
        return None, True, text
    first, second, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
    if year < 100:
        year += 2000
    if first > 31 or second > 31 or not 2000 <= year <= 2100:
        return None, True, text
    if first > 12 and second > 12:
        return None, True, text
    if first > 12:
        day, month, ambiguous = first, second, False
    elif second > 12:
        day, month, ambiguous = second, first, False
    else:
        return None, True, text
    try:
        return date(year, month, day).isoformat(), ambiguous, text
    except ValueError:
        return None, True, text


def local_clock_status(day: str, clock: str) -> str:
    """Return '', 'time_gap' or 'time_fold' for a Europe/London local clock time."""
    naive = datetime.fromisoformat(f'{day}T{clock}')
    aware = naive.replace(tzinfo=ZONE)
    # A spring-forward gap also differs by fold in zoneinfo, so the missing
    # local time has to be detected before the repeated autumn time.
    round_trip = aware.astimezone(timezone.utc).astimezone(ZONE).replace(tzinfo=None)
    if round_trip != naive:
        return 'time_gap'
    if aware.replace(fold=0).astimezone(timezone.utc) != aware.replace(fold=1).astimezone(timezone.utc):
        return 'time_fold'
    return ''


def _clock_status(work_date, start, end) -> str:
    if not work_date or not start:
        return ''
    start_status = local_clock_status(work_date, start)
    if start_status:
        return start_status
    if not end:
        return ''
    end_day = work_date
    if end <= start:
        end_day = (date.fromisoformat(work_date) + timedelta(days=1)).isoformat()
    return local_clock_status(end_day, end)


def _map_headers(headers):
    mapping = {}
    for index, header in enumerate(headers):
        key = _header_key(header)
        if key in _NAME_HEADERS:
            mapping[index] = 'name'
        elif key in _DATE_HEADERS:
            mapping[index] = 'date'
        elif key in _START_HEADERS:
            mapping[index] = 'start'
        elif key in _END_HEADERS:
            mapping[index] = 'end'
        elif key in _LABEL_HEADERS:
            mapping[index] = 'label'
        elif key in _DEPARTMENT_HEADERS:
            mapping[index] = 'department'
        elif key in _LOCATION_HEADERS:
            mapping[index] = 'location'
        elif key in _KIND_HEADERS:
            mapping[index] = 'kind'
    return mapping


def _row_dict(cells, mapping):
    item = {}
    for index, field in mapping.items():
        if index < len(cells) and cells[index] not in (None, ''):
            item[field] = cells[index]
    return item


def interpret_table(rows):
    """Turn a headered or positional table into draft entries.

    A name column with more than one person is refused before any name is kept.
    Blank rows are skipped and are not treated as days off.
    """
    if not rows:
        raise ParseProblem('No rows were found in this file.', 'unrecognized_table')
    header_map = _map_headers(rows[0])
    data_rows = rows[1:] if {'date', 'start'} & set(header_map.values()) else None
    if data_rows is None:
        header_map = {0: 'date', 1: 'start', 2: 'end', 3: 'label', 4: 'department', 5: 'location', 6: 'kind'}
        data_rows = rows
    name_indexes = [index for index, field in header_map.items() if field == 'name']
    if name_indexes:
        names = set()
        for cells in data_rows:
            for index in name_indexes:
                if index < len(cells) and clean_text(cells[index], 80):
                    names.add(clean_text(cells[index], 80).casefold())
        if len(names) > 1:
            raise ParseProblem(
                'This file looks like a shared rota. Align only imports your own rows. Remove other people and upload it again.',
                'multiple_people',
            )
    drafts = []
    for cells in data_rows:
        if not any(clean_text(cell, 20) for cell in cells):
            continue
        item = _row_dict(cells, header_map)
        item.pop('name', None)
        if not any(item.get(key) for key in ('date', 'start', 'end', 'label', 'department', 'location', 'kind')):
            continue
        drafts.append(_draft_from_fields(item))
    if not drafts:
        raise ParseProblem('No shift rows were found. Empty cells are not treated as days off.', 'unrecognized_table')
    return drafts


def interpret_pdf_text(text: str):
    lines = [clean_text(line, 240) for line in str(text or '').splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        raise ParseProblem('This PDF has no readable text. Scanned PDFs need local image reading.', 'ocr_unavailable')
    # OCR must not silently import several colleagues' rows into one account.
    # A tabular name/employee header is treated conservatively and requires
    # the user to crop or export only their own rows before uploading.
    if any(
        re.search(r'\\b(?:name|employee|staff)\\b', line, re.IGNORECASE)
        and re.search(r'\\b(?:date|day|shift|start|time)\\b', line, re.IGNORECASE)
        for line in lines
    ):
        raise ParseProblem(
            'This looks like a shared rota. Crop or export only your own rows before uploading.',
            'multiple_people',
        )
    named_rows = {
        clean_text(match.group(1), 80).casefold()
        for line in lines
        if (match := re.match(r'^(?:name|employee|staff)\\s*[:=-]\\s*(.+)        r'(?:(?:Mon(?:day)?|Tue(?:sday)?|Wed(?:nesday)?|Thu(?:rsday)?|Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?)\\s+)?'
        r'(?P<date>\\d{4}-\\d{2}-\\d{2}|\\d{1,2}[/-]\\d{1,2}[/-]\\d{2,4}|'
        r'\\d{1,2}\\s+[A-Za-z]{3,9}\\s+\\d{4}|[A-Za-z]{3,9}\\s+\\d{1,2},?\\s+\\d{4})'
        r'(?:\\s+(?P<start>\\d{1,2}[:.]\\d{2})(?:\\s*[-–]\\s*|\\s+to\\s+|\\s+)(?P<end>\\d{1,2}[:.]\\d{2}))?'
        r'(?:\\s+(?P<rest>.+))?$',
        re.IGNORECASE,
    )
    drafts = []
    for line in lines:
        match = pattern.search(line)
        if not match:
            continue
        rest = clean_text(match.group('rest') or '', 160)
        label, department, location = rest, '', ''
        if ' at ' in rest:
            label, location = rest.split(' at ', 1)
        elif ',' in rest:
            parts = [clean_text(part, 80) for part in rest.split(',')]
            label = parts[0] if parts else ''
            department = parts[1] if len(parts) > 1 else ''
            location = parts[2] if len(parts) > 2 else ''
        drafts.append(_draft_from_fields({
            'date': match.group('date'),
            'start': match.group('start') or '',
            'end': match.group('end') or '',
            'label': label,
            'department': department,
            'location': location,
        }))
    if not drafts:
        raise ParseProblem('No dated shifts were found in this PDF or photo.', 'unrecognized_table')
    return drafts

def _draft_from_fields(item):
    work_date, date_ambiguous, source_date = parse_date(item.get('date', ''))
    start = parse_clock(item.get('start', ''))
    end = parse_clock(item.get('end', ''))
    label = clean_text(item.get('label', ''), 80)
    department = clean_text(item.get('department', ''), 80)
    location_text = clean_text(item.get('location', ''), 120)
    explicit = _kind_token(item.get('kind', '')) or _kind_token(label)
    if explicit in {'day_off', 'leave', 'sickness'}:
        kind = explicit
    elif start and end:
        kind = 'shift'
    elif explicit == 'shift':
        kind = 'shift'
    else:
        kind = 'unknown'
    ambiguity = 'date' if date_ambiguous else _clock_status(work_date, start, end)
    return {
        'work_date': work_date,
        'source_date_text': source_date,
        'start_time': start or '',
        'end_time': end or '',
        'shift_label': label,
        'department': department,
        'location_text': location_text,
        'entry_kind': kind,
        'ambiguity': ambiguity,
        'location_id': None,
        'shift_type_id': None,
        'template_id': None,
    }


def _one_match(needle, rows, field):
    text = clean_text(needle, 120).casefold()
    if len(text) < 2:
        return None
    exact = [row for row in rows if clean_text(row.get(field, ''), 120).casefold() == text]
    if len(exact) == 1:
        return exact[0]
    if len(text) < 4:
        return None
    contained = [
        row for row in rows
        if text in clean_text(row.get(field, ''), 120).casefold()
        or clean_text(row.get(field, ''), 120).casefold() in text
    ]
    if len(contained) == 1:
        return contained[0]
    return None


def match_catalog(draft, catalog):
    """Link a location, shift type or template only on one clear match."""
    matched = dict(draft)
    locations = [row for row in catalog.get('locations', []) if row.get('active', 1)]
    shift_types = [row for row in catalog.get('shift_types', []) if row.get('active', 1)]
    templates = [row for row in catalog.get('templates', []) if row.get('active', 1)]
    location = _one_match(matched.get('location_text', ''), locations, 'name')
    if location:
        matched['location_id'] = location['id']
        matched['location_text'] = location['name']
    pool = templates
    if matched.get('location_id'):
        pool = [row for row in templates if row.get('location_id') == matched['location_id']] or templates
    template = None
    if matched.get('start_time') and matched.get('end_time'):
        timed = [
            row for row in pool
            if row.get('start_time') == matched['start_time'] and row.get('end_time') == matched['end_time']
        ]
        labelled = [row for row in timed if matched.get('shift_label') and clean_text(row.get('label', ''), 80).casefold() == matched['shift_label'].casefold()]
        if len(labelled) == 1:
            template = labelled[0]
        elif len(timed) == 1 and not matched.get('shift_label'):
            template = timed[0]
    if template:
        matched['template_id'] = template['id']
        matched['location_id'] = template['location_id']
        matched['shift_type_id'] = template['shift_type_id']
    if not matched.get('shift_type_id'):
        shift_type = _one_match(matched.get('department', ''), shift_types, 'name') or _one_match(matched.get('shift_label', ''), shift_types, 'name')
        if shift_type:
            matched['shift_type_id'] = shift_type['id']
    return score_entry(matched)


def score_entry(entry):
    scored = dict(entry)
    kind = scored.get('entry_kind') or 'unknown'
    missing_shift_time = kind == 'shift' and (not scored.get('work_date') or not scored.get('start_time') or not scored.get('end_time'))
    if kind == 'unknown' or missing_shift_time or scored.get('ambiguity') == 'date' and not scored.get('work_date'):
        confidence = 0.25
    elif scored.get('ambiguity'):
        confidence = 0.45
    elif kind == 'shift' and (not scored.get('location_id') or not scored.get('shift_type_id')):
        confidence = 0.72
    elif kind == 'shift':
        confidence = 0.93
    elif kind in {'day_off', 'leave', 'sickness'} and scored.get('work_date'):
        confidence = 0.9
    else:
        confidence = 0.4
    scored['confidence'] = round(confidence, 2)
    scored['approvable'] = int(_approvable(scored))
    scored['preselected'] = int(scored['approvable'] and confidence >= HIGH_CONFIDENCE)
    scored['confidence_band'] = 'high' if confidence >= HIGH_CONFIDENCE else 'medium' if confidence >= MEDIUM_CONFIDENCE else 'low'
    scored['fingerprint'] = '|'.join([
        kind,
        scored.get('work_date') or '',
        scored.get('start_time') or '',
        scored.get('end_time') or '',
        str(scored.get('location_id') or clean_text(scored.get('location_text', ''), 120).casefold()),
    ])
    return scored


def _approvable(entry) -> bool:
    if entry.get('duplicate_shift_id') or entry.get('review_status') == 'rejected':
        return False
    if entry.get('ambiguity'):
        return False
    if float(entry.get('confidence') or 0) < MEDIUM_CONFIDENCE:
        return False
    kind = entry.get('entry_kind')
    if kind == 'shift':
        return bool(entry.get('work_date') and entry.get('start_time') and entry.get('end_time') and entry.get('location_id') and entry.get('shift_type_id'))
    if kind in {'day_off', 'leave', 'sickness'}:
        return bool(entry.get('work_date'))
    return False


def apply_correction(entry, patch):
    """Apply a reviewed correction. An explicit ISO date resolves a date ambiguity."""
    updated = dict(entry)
    if 'work_date' in patch:
        text = clean_text(patch.get('work_date'), 40)
        if text:
            try:
                updated['work_date'] = date.fromisoformat(text).isoformat()
            except ValueError as error:
                raise ParseProblem('Enter the date as YYYY-MM-DD.', 'invalid_date') from error
            if updated.get('ambiguity') == 'date':
                updated['ambiguity'] = ''
        else:
            updated['work_date'] = None
    for field, limit in (('start_time', 5), ('end_time', 5)):
        if field in patch:
            clock = parse_clock(patch.get(field))
            if patch.get(field) not in ('', None) and not clock:
                raise ParseProblem('Enter times as HH:MM.', 'invalid_time')
            updated[field] = clock or ''
    for field, limit in (('shift_label', 80), ('department', 80), ('location_text', 120)):
        if field in patch:
            updated[field] = clean_text(patch.get(field), limit)
    if 'entry_kind' in patch:
        kind = str(patch.get('entry_kind') or '')
        if kind not in KINDS:
            raise ParseProblem('Choose shift, day off, leave, sickness or unknown.', 'invalid_kind')
        updated['entry_kind'] = kind
    if 'location_id' in patch:
        updated['location_id'] = patch.get('location_id') or None
    if 'shift_type_id' in patch:
        updated['shift_type_id'] = patch.get('shift_type_id') or None
    if 'template_id' in patch:
        updated['template_id'] = patch.get('template_id') or None
    if updated.get('work_date') and updated.get('start_time'):
        clock_issue = _clock_status(updated['work_date'], updated['start_time'], updated.get('end_time') or '')
        if clock_issue == 'time_fold' and patch.get('confirm_ambiguity'):
            updated['ambiguity'] = ''
        elif clock_issue:
            updated['ambiguity'] = clock_issue
        elif updated.get('ambiguity') in {'time_gap', 'time_fold'}:
            updated['ambiguity'] = ''
    if 'review_status' in patch:
        status = str(patch.get('review_status') or '')
        if status not in {'pending', 'rejected'}:
            raise ParseProblem('Choose pending or rejected.', 'invalid_review')
        updated['review_status'] = status
    updated['duplicate_shift_id'] = None
    return score_entry(updated)
,
        re.IGNORECASE,
    )
    drafts = []
    for line in lines:
        match = pattern.search(line)
        if not match:
            continue
        rest = clean_text(match.group('rest') or '', 160)
        label, department, location = rest, '', ''
        if ' at ' in rest:
            label, location = rest.split(' at ', 1)
        elif ',' in rest:
            parts = [clean_text(part, 80) for part in rest.split(',')]
            label = parts[0] if parts else ''
            department = parts[1] if len(parts) > 1 else ''
            location = parts[2] if len(parts) > 2 else ''
        drafts.append(_draft_from_fields({
            'date': match.group('date'),
            'start': match.group('start') or '',
            'end': match.group('end') or '',
            'label': label,
            'department': department,
            'location': location,
        }))
    if not drafts:
        raise ParseProblem('No dated shifts were found in this PDF.', 'unrecognized_table')
    return drafts


def _draft_from_fields(item):
    work_date, date_ambiguous, source_date = parse_date(item.get('date', ''))
    start = parse_clock(item.get('start', ''))
    end = parse_clock(item.get('end', ''))
    label = clean_text(item.get('label', ''), 80)
    department = clean_text(item.get('department', ''), 80)
    location_text = clean_text(item.get('location', ''), 120)
    explicit = _kind_token(item.get('kind', '')) or _kind_token(label)
    if explicit in {'day_off', 'leave', 'sickness'}:
        kind = explicit
    elif start and end:
        kind = 'shift'
    elif explicit == 'shift':
        kind = 'shift'
    else:
        kind = 'unknown'
    ambiguity = 'date' if date_ambiguous else _clock_status(work_date, start, end)
    return {
        'work_date': work_date,
        'source_date_text': source_date,
        'start_time': start or '',
        'end_time': end or '',
        'shift_label': label,
        'department': department,
        'location_text': location_text,
        'entry_kind': kind,
        'ambiguity': ambiguity,
        'location_id': None,
        'shift_type_id': None,
        'template_id': None,
    }


def _one_match(needle, rows, field):
    text = clean_text(needle, 120).casefold()
    if len(text) < 2:
        return None
    exact = [row for row in rows if clean_text(row.get(field, ''), 120).casefold() == text]
    if len(exact) == 1:
        return exact[0]
    if len(text) < 4:
        return None
    contained = [
        row for row in rows
        if text in clean_text(row.get(field, ''), 120).casefold()
        or clean_text(row.get(field, ''), 120).casefold() in text
    ]
    if len(contained) == 1:
        return contained[0]
    return None


def match_catalog(draft, catalog):
    """Link a location, shift type or template only on one clear match."""
    matched = dict(draft)
    locations = [row for row in catalog.get('locations', []) if row.get('active', 1)]
    shift_types = [row for row in catalog.get('shift_types', []) if row.get('active', 1)]
    templates = [row for row in catalog.get('templates', []) if row.get('active', 1)]
    location = _one_match(matched.get('location_text', ''), locations, 'name')
    if location:
        matched['location_id'] = location['id']
        matched['location_text'] = location['name']
    pool = templates
    if matched.get('location_id'):
        pool = [row for row in templates if row.get('location_id') == matched['location_id']] or templates
    template = None
    if matched.get('start_time') and matched.get('end_time'):
        timed = [
            row for row in pool
            if row.get('start_time') == matched['start_time'] and row.get('end_time') == matched['end_time']
        ]
        labelled = [row for row in timed if matched.get('shift_label') and clean_text(row.get('label', ''), 80).casefold() == matched['shift_label'].casefold()]
        if len(labelled) == 1:
            template = labelled[0]
        elif len(timed) == 1 and not matched.get('shift_label'):
            template = timed[0]
    if template:
        matched['template_id'] = template['id']
        matched['location_id'] = template['location_id']
        matched['shift_type_id'] = template['shift_type_id']
    if not matched.get('shift_type_id'):
        shift_type = _one_match(matched.get('department', ''), shift_types, 'name') or _one_match(matched.get('shift_label', ''), shift_types, 'name')
        if shift_type:
            matched['shift_type_id'] = shift_type['id']
    return score_entry(matched)


def score_entry(entry):
    scored = dict(entry)
    kind = scored.get('entry_kind') or 'unknown'
    missing_shift_time = kind == 'shift' and (not scored.get('work_date') or not scored.get('start_time') or not scored.get('end_time'))
    if kind == 'unknown' or missing_shift_time or scored.get('ambiguity') == 'date' and not scored.get('work_date'):
        confidence = 0.25
    elif scored.get('ambiguity'):
        confidence = 0.45
    elif kind == 'shift' and (not scored.get('location_id') or not scored.get('shift_type_id')):
        confidence = 0.72
    elif kind == 'shift':
        confidence = 0.93
    elif kind in {'day_off', 'leave', 'sickness'} and scored.get('work_date'):
        confidence = 0.9
    else:
        confidence = 0.4
    scored['confidence'] = round(confidence, 2)
    scored['approvable'] = int(_approvable(scored))
    scored['preselected'] = int(scored['approvable'] and confidence >= HIGH_CONFIDENCE)
    scored['confidence_band'] = 'high' if confidence >= HIGH_CONFIDENCE else 'medium' if confidence >= MEDIUM_CONFIDENCE else 'low'
    scored['fingerprint'] = '|'.join([
        kind,
        scored.get('work_date') or '',
        scored.get('start_time') or '',
        scored.get('end_time') or '',
        str(scored.get('location_id') or clean_text(scored.get('location_text', ''), 120).casefold()),
    ])
    return scored


def _approvable(entry) -> bool:
    if entry.get('duplicate_shift_id') or entry.get('review_status') == 'rejected':
        return False
    if entry.get('ambiguity'):
        return False
    if float(entry.get('confidence') or 0) < MEDIUM_CONFIDENCE:
        return False
    kind = entry.get('entry_kind')
    if kind == 'shift':
        return bool(entry.get('work_date') and entry.get('start_time') and entry.get('end_time') and entry.get('location_id') and entry.get('shift_type_id'))
    if kind in {'day_off', 'leave', 'sickness'}:
        return bool(entry.get('work_date'))
    return False


def apply_correction(entry, patch):
    """Apply a reviewed correction. An explicit ISO date resolves a date ambiguity."""
    updated = dict(entry)
    if 'work_date' in patch:
        text = clean_text(patch.get('work_date'), 40)
        if text:
            try:
                updated['work_date'] = date.fromisoformat(text).isoformat()
            except ValueError as error:
                raise ParseProblem('Enter the date as YYYY-MM-DD.', 'invalid_date') from error
            if updated.get('ambiguity') == 'date':
                updated['ambiguity'] = ''
        else:
            updated['work_date'] = None
    for field, limit in (('start_time', 5), ('end_time', 5)):
        if field in patch:
            clock = parse_clock(patch.get(field))
            if patch.get(field) not in ('', None) and not clock:
                raise ParseProblem('Enter times as HH:MM.', 'invalid_time')
            updated[field] = clock or ''
    for field, limit in (('shift_label', 80), ('department', 80), ('location_text', 120)):
        if field in patch:
            updated[field] = clean_text(patch.get(field), limit)
    if 'entry_kind' in patch:
        kind = str(patch.get('entry_kind') or '')
        if kind not in KINDS:
            raise ParseProblem('Choose shift, day off, leave, sickness or unknown.', 'invalid_kind')
        updated['entry_kind'] = kind
    if 'location_id' in patch:
        updated['location_id'] = patch.get('location_id') or None
    if 'shift_type_id' in patch:
        updated['shift_type_id'] = patch.get('shift_type_id') or None
    if 'template_id' in patch:
        updated['template_id'] = patch.get('template_id') or None
    if updated.get('work_date') and updated.get('start_time'):
        clock_issue = _clock_status(updated['work_date'], updated['start_time'], updated.get('end_time') or '')
        if clock_issue == 'time_fold' and patch.get('confirm_ambiguity'):
            updated['ambiguity'] = ''
        elif clock_issue:
            updated['ambiguity'] = clock_issue
        elif updated.get('ambiguity') in {'time_gap', 'time_fold'}:
            updated['ambiguity'] = ''
    if 'review_status' in patch:
        status = str(patch.get('review_status') or '')
        if status not in {'pending', 'rejected'}:
            raise ParseProblem('Choose pending or rejected.', 'invalid_review')
        updated['review_status'] = status
    updated['duplicate_shift_id'] = None
    return score_entry(updated)
, line, re.IGNORECASE))
    }
    if len(named_rows) > 1:
        raise ParseProblem(
            'This file contains more than one person. Upload only your own rota rows.',
            'multiple_people',
        )
    pattern = re.compile(
        r'(?:(?:Mon(?:day)?|Tue(?:sday)?|Wed(?:nesday)?|Thu(?:rsday)?|Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?)\\s+)?'
        r'(?P<date>\\d{4}-\\d{2}-\\d{2}|\\d{1,2}[/-]\\d{1,2}[/-]\\d{2,4}|'
        r'\\d{1,2}\\s+[A-Za-z]{3,9}\\s+\\d{4}|[A-Za-z]{3,9}\\s+\\d{1,2},?\\s+\\d{4})'
        r'(?:\\s+(?P<start>\\d{1,2}[:.]\\d{2})(?:\\s*[-–]\\s*|\\s+to\\s+|\\s+)(?P<end>\\d{1,2}[:.]\\d{2}))?'
        r'(?:\\s+(?P<rest>.+))?$',
        re.IGNORECASE,
    )
    drafts = []
    for line in lines:
        match = pattern.search(line)
        if not match:
            continue
        rest = clean_text(match.group('rest') or '', 160)
        label, department, location = rest, '', ''
        if ' at ' in rest:
            label, location = rest.split(' at ', 1)
        elif ',' in rest:
            parts = [clean_text(part, 80) for part in rest.split(',')]
            label = parts[0] if parts else ''
            department = parts[1] if len(parts) > 1 else ''
            location = parts[2] if len(parts) > 2 else ''
        drafts.append(_draft_from_fields({
            'date': match.group('date'),
            'start': match.group('start') or '',
            'end': match.group('end') or '',
            'label': label,
            'department': department,
            'location': location,
        }))
    if not drafts:
        raise ParseProblem('No dated shifts were found in this PDF or photo.', 'unrecognized_table')
    return drafts

def _draft_from_fields(item):
    work_date, date_ambiguous, source_date = parse_date(item.get('date', ''))
    start = parse_clock(item.get('start', ''))
    end = parse_clock(item.get('end', ''))
    label = clean_text(item.get('label', ''), 80)
    department = clean_text(item.get('department', ''), 80)
    location_text = clean_text(item.get('location', ''), 120)
    explicit = _kind_token(item.get('kind', '')) or _kind_token(label)
    if explicit in {'day_off', 'leave', 'sickness'}:
        kind = explicit
    elif start and end:
        kind = 'shift'
    elif explicit == 'shift':
        kind = 'shift'
    else:
        kind = 'unknown'
    ambiguity = 'date' if date_ambiguous else _clock_status(work_date, start, end)
    return {
        'work_date': work_date,
        'source_date_text': source_date,
        'start_time': start or '',
        'end_time': end or '',
        'shift_label': label,
        'department': department,
        'location_text': location_text,
        'entry_kind': kind,
        'ambiguity': ambiguity,
        'location_id': None,
        'shift_type_id': None,
        'template_id': None,
    }


def _one_match(needle, rows, field):
    text = clean_text(needle, 120).casefold()
    if len(text) < 2:
        return None
    exact = [row for row in rows if clean_text(row.get(field, ''), 120).casefold() == text]
    if len(exact) == 1:
        return exact[0]
    if len(text) < 4:
        return None
    contained = [
        row for row in rows
        if text in clean_text(row.get(field, ''), 120).casefold()
        or clean_text(row.get(field, ''), 120).casefold() in text
    ]
    if len(contained) == 1:
        return contained[0]
    return None


def match_catalog(draft, catalog):
    """Link a location, shift type or template only on one clear match."""
    matched = dict(draft)
    locations = [row for row in catalog.get('locations', []) if row.get('active', 1)]
    shift_types = [row for row in catalog.get('shift_types', []) if row.get('active', 1)]
    templates = [row for row in catalog.get('templates', []) if row.get('active', 1)]
    location = _one_match(matched.get('location_text', ''), locations, 'name')
    if location:
        matched['location_id'] = location['id']
        matched['location_text'] = location['name']
    pool = templates
    if matched.get('location_id'):
        pool = [row for row in templates if row.get('location_id') == matched['location_id']] or templates
    template = None
    if matched.get('start_time') and matched.get('end_time'):
        timed = [
            row for row in pool
            if row.get('start_time') == matched['start_time'] and row.get('end_time') == matched['end_time']
        ]
        labelled = [row for row in timed if matched.get('shift_label') and clean_text(row.get('label', ''), 80).casefold() == matched['shift_label'].casefold()]
        if len(labelled) == 1:
            template = labelled[0]
        elif len(timed) == 1 and not matched.get('shift_label'):
            template = timed[0]
    if template:
        matched['template_id'] = template['id']
        matched['location_id'] = template['location_id']
        matched['shift_type_id'] = template['shift_type_id']
    if not matched.get('shift_type_id'):
        shift_type = _one_match(matched.get('department', ''), shift_types, 'name') or _one_match(matched.get('shift_label', ''), shift_types, 'name')
        if shift_type:
            matched['shift_type_id'] = shift_type['id']
    return score_entry(matched)


def score_entry(entry):
    scored = dict(entry)
    kind = scored.get('entry_kind') or 'unknown'
    missing_shift_time = kind == 'shift' and (not scored.get('work_date') or not scored.get('start_time') or not scored.get('end_time'))
    if kind == 'unknown' or missing_shift_time or scored.get('ambiguity') == 'date' and not scored.get('work_date'):
        confidence = 0.25
    elif scored.get('ambiguity'):
        confidence = 0.45
    elif kind == 'shift' and (not scored.get('location_id') or not scored.get('shift_type_id')):
        confidence = 0.72
    elif kind == 'shift':
        confidence = 0.93
    elif kind in {'day_off', 'leave', 'sickness'} and scored.get('work_date'):
        confidence = 0.9
    else:
        confidence = 0.4
    scored['confidence'] = round(confidence, 2)
    scored['approvable'] = int(_approvable(scored))
    scored['preselected'] = int(scored['approvable'] and confidence >= HIGH_CONFIDENCE)
    scored['confidence_band'] = 'high' if confidence >= HIGH_CONFIDENCE else 'medium' if confidence >= MEDIUM_CONFIDENCE else 'low'
    scored['fingerprint'] = '|'.join([
        kind,
        scored.get('work_date') or '',
        scored.get('start_time') or '',
        scored.get('end_time') or '',
        str(scored.get('location_id') or clean_text(scored.get('location_text', ''), 120).casefold()),
    ])
    return scored


def _approvable(entry) -> bool:
    if entry.get('duplicate_shift_id') or entry.get('review_status') == 'rejected':
        return False
    if entry.get('ambiguity'):
        return False
    if float(entry.get('confidence') or 0) < MEDIUM_CONFIDENCE:
        return False
    kind = entry.get('entry_kind')
    if kind == 'shift':
        return bool(entry.get('work_date') and entry.get('start_time') and entry.get('end_time') and entry.get('location_id') and entry.get('shift_type_id'))
    if kind in {'day_off', 'leave', 'sickness'}:
        return bool(entry.get('work_date'))
    return False


def apply_correction(entry, patch):
    """Apply a reviewed correction. An explicit ISO date resolves a date ambiguity."""
    updated = dict(entry)
    if 'work_date' in patch:
        text = clean_text(patch.get('work_date'), 40)
        if text:
            try:
                updated['work_date'] = date.fromisoformat(text).isoformat()
            except ValueError as error:
                raise ParseProblem('Enter the date as YYYY-MM-DD.', 'invalid_date') from error
            if updated.get('ambiguity') == 'date':
                updated['ambiguity'] = ''
        else:
            updated['work_date'] = None
    for field, limit in (('start_time', 5), ('end_time', 5)):
        if field in patch:
            clock = parse_clock(patch.get(field))
            if patch.get(field) not in ('', None) and not clock:
                raise ParseProblem('Enter times as HH:MM.', 'invalid_time')
            updated[field] = clock or ''
    for field, limit in (('shift_label', 80), ('department', 80), ('location_text', 120)):
        if field in patch:
            updated[field] = clean_text(patch.get(field), limit)
    if 'entry_kind' in patch:
        kind = str(patch.get('entry_kind') or '')
        if kind not in KINDS:
            raise ParseProblem('Choose shift, day off, leave, sickness or unknown.', 'invalid_kind')
        updated['entry_kind'] = kind
    if 'location_id' in patch:
        updated['location_id'] = patch.get('location_id') or None
    if 'shift_type_id' in patch:
        updated['shift_type_id'] = patch.get('shift_type_id') or None
    if 'template_id' in patch:
        updated['template_id'] = patch.get('template_id') or None
    if updated.get('work_date') and updated.get('start_time'):
        clock_issue = _clock_status(updated['work_date'], updated['start_time'], updated.get('end_time') or '')
        if clock_issue == 'time_fold' and patch.get('confirm_ambiguity'):
            updated['ambiguity'] = ''
        elif clock_issue:
            updated['ambiguity'] = clock_issue
        elif updated.get('ambiguity') in {'time_gap', 'time_fold'}:
            updated['ambiguity'] = ''
    if 'review_status' in patch:
        status = str(patch.get('review_status') or '')
        if status not in {'pending', 'rejected'}:
            raise ParseProblem('Choose pending or rejected.', 'invalid_review')
        updated['review_status'] = status
    updated['duplicate_shift_id'] = None
    return score_entry(updated)
,
        re.IGNORECASE,
    )
    drafts = []
    for line in lines:
        match = pattern.search(line)
        if not match:
            continue
        rest = clean_text(match.group('rest') or '', 160)
        label, department, location = rest, '', ''
        if ' at ' in rest:
            label, location = rest.split(' at ', 1)
        elif ',' in rest:
            parts = [clean_text(part, 80) for part in rest.split(',')]
            label = parts[0] if parts else ''
            department = parts[1] if len(parts) > 1 else ''
            location = parts[2] if len(parts) > 2 else ''
        drafts.append(_draft_from_fields({
            'date': match.group('date'),
            'start': match.group('start') or '',
            'end': match.group('end') or '',
            'label': label,
            'department': department,
            'location': location,
        }))
    if not drafts:
        raise ParseProblem('No dated shifts were found in this PDF.', 'unrecognized_table')
    return drafts


def _draft_from_fields(item):
    work_date, date_ambiguous, source_date = parse_date(item.get('date', ''))
    start = parse_clock(item.get('start', ''))
    end = parse_clock(item.get('end', ''))
    label = clean_text(item.get('label', ''), 80)
    department = clean_text(item.get('department', ''), 80)
    location_text = clean_text(item.get('location', ''), 120)
    explicit = _kind_token(item.get('kind', '')) or _kind_token(label)
    if explicit in {'day_off', 'leave', 'sickness'}:
        kind = explicit
    elif start and end:
        kind = 'shift'
    elif explicit == 'shift':
        kind = 'shift'
    else:
        kind = 'unknown'
    ambiguity = 'date' if date_ambiguous else _clock_status(work_date, start, end)
    return {
        'work_date': work_date,
        'source_date_text': source_date,
        'start_time': start or '',
        'end_time': end or '',
        'shift_label': label,
        'department': department,
        'location_text': location_text,
        'entry_kind': kind,
        'ambiguity': ambiguity,
        'location_id': None,
        'shift_type_id': None,
        'template_id': None,
    }


def _one_match(needle, rows, field):
    text = clean_text(needle, 120).casefold()
    if len(text) < 2:
        return None
    exact = [row for row in rows if clean_text(row.get(field, ''), 120).casefold() == text]
    if len(exact) == 1:
        return exact[0]
    if len(text) < 4:
        return None
    contained = [
        row for row in rows
        if text in clean_text(row.get(field, ''), 120).casefold()
        or clean_text(row.get(field, ''), 120).casefold() in text
    ]
    if len(contained) == 1:
        return contained[0]
    return None


def match_catalog(draft, catalog):
    """Link a location, shift type or template only on one clear match."""
    matched = dict(draft)
    locations = [row for row in catalog.get('locations', []) if row.get('active', 1)]
    shift_types = [row for row in catalog.get('shift_types', []) if row.get('active', 1)]
    templates = [row for row in catalog.get('templates', []) if row.get('active', 1)]
    location = _one_match(matched.get('location_text', ''), locations, 'name')
    if location:
        matched['location_id'] = location['id']
        matched['location_text'] = location['name']
    pool = templates
    if matched.get('location_id'):
        pool = [row for row in templates if row.get('location_id') == matched['location_id']] or templates
    template = None
    if matched.get('start_time') and matched.get('end_time'):
        timed = [
            row for row in pool
            if row.get('start_time') == matched['start_time'] and row.get('end_time') == matched['end_time']
        ]
        labelled = [row for row in timed if matched.get('shift_label') and clean_text(row.get('label', ''), 80).casefold() == matched['shift_label'].casefold()]
        if len(labelled) == 1:
            template = labelled[0]
        elif len(timed) == 1 and not matched.get('shift_label'):
            template = timed[0]
    if template:
        matched['template_id'] = template['id']
        matched['location_id'] = template['location_id']
        matched['shift_type_id'] = template['shift_type_id']
    if not matched.get('shift_type_id'):
        shift_type = _one_match(matched.get('department', ''), shift_types, 'name') or _one_match(matched.get('shift_label', ''), shift_types, 'name')
        if shift_type:
            matched['shift_type_id'] = shift_type['id']
    return score_entry(matched)


def score_entry(entry):
    scored = dict(entry)
    kind = scored.get('entry_kind') or 'unknown'
    missing_shift_time = kind == 'shift' and (not scored.get('work_date') or not scored.get('start_time') or not scored.get('end_time'))
    if kind == 'unknown' or missing_shift_time or scored.get('ambiguity') == 'date' and not scored.get('work_date'):
        confidence = 0.25
    elif scored.get('ambiguity'):
        confidence = 0.45
    elif kind == 'shift' and (not scored.get('location_id') or not scored.get('shift_type_id')):
        confidence = 0.72
    elif kind == 'shift':
        confidence = 0.93
    elif kind in {'day_off', 'leave', 'sickness'} and scored.get('work_date'):
        confidence = 0.9
    else:
        confidence = 0.4
    scored['confidence'] = round(confidence, 2)
    scored['approvable'] = int(_approvable(scored))
    scored['preselected'] = int(scored['approvable'] and confidence >= HIGH_CONFIDENCE)
    scored['confidence_band'] = 'high' if confidence >= HIGH_CONFIDENCE else 'medium' if confidence >= MEDIUM_CONFIDENCE else 'low'
    scored['fingerprint'] = '|'.join([
        kind,
        scored.get('work_date') or '',
        scored.get('start_time') or '',
        scored.get('end_time') or '',
        str(scored.get('location_id') or clean_text(scored.get('location_text', ''), 120).casefold()),
    ])
    return scored


def _approvable(entry) -> bool:
    if entry.get('duplicate_shift_id') or entry.get('review_status') == 'rejected':
        return False
    if entry.get('ambiguity'):
        return False
    if float(entry.get('confidence') or 0) < MEDIUM_CONFIDENCE:
        return False
    kind = entry.get('entry_kind')
    if kind == 'shift':
        return bool(entry.get('work_date') and entry.get('start_time') and entry.get('end_time') and entry.get('location_id') and entry.get('shift_type_id'))
    if kind in {'day_off', 'leave', 'sickness'}:
        return bool(entry.get('work_date'))
    return False


def apply_correction(entry, patch):
    """Apply a reviewed correction. An explicit ISO date resolves a date ambiguity."""
    updated = dict(entry)
    if 'work_date' in patch:
        text = clean_text(patch.get('work_date'), 40)
        if text:
            try:
                updated['work_date'] = date.fromisoformat(text).isoformat()
            except ValueError as error:
                raise ParseProblem('Enter the date as YYYY-MM-DD.', 'invalid_date') from error
            if updated.get('ambiguity') == 'date':
                updated['ambiguity'] = ''
        else:
            updated['work_date'] = None
    for field, limit in (('start_time', 5), ('end_time', 5)):
        if field in patch:
            clock = parse_clock(patch.get(field))
            if patch.get(field) not in ('', None) and not clock:
                raise ParseProblem('Enter times as HH:MM.', 'invalid_time')
            updated[field] = clock or ''
    for field, limit in (('shift_label', 80), ('department', 80), ('location_text', 120)):
        if field in patch:
            updated[field] = clean_text(patch.get(field), limit)
    if 'entry_kind' in patch:
        kind = str(patch.get('entry_kind') or '')
        if kind not in KINDS:
            raise ParseProblem('Choose shift, day off, leave, sickness or unknown.', 'invalid_kind')
        updated['entry_kind'] = kind
    if 'location_id' in patch:
        updated['location_id'] = patch.get('location_id') or None
    if 'shift_type_id' in patch:
        updated['shift_type_id'] = patch.get('shift_type_id') or None
    if 'template_id' in patch:
        updated['template_id'] = patch.get('template_id') or None
    if updated.get('work_date') and updated.get('start_time'):
        clock_issue = _clock_status(updated['work_date'], updated['start_time'], updated.get('end_time') or '')
        if clock_issue == 'time_fold' and patch.get('confirm_ambiguity'):
            updated['ambiguity'] = ''
        elif clock_issue:
            updated['ambiguity'] = clock_issue
        elif updated.get('ambiguity') in {'time_gap', 'time_fold'}:
            updated['ambiguity'] = ''
    if 'review_status' in patch:
        status = str(patch.get('review_status') or '')
        if status not in {'pending', 'rejected'}:
            raise ParseProblem('Choose pending or rejected.', 'invalid_review')
        updated['review_status'] = status
    updated['duplicate_shift_id'] = None
    return score_entry(updated)
