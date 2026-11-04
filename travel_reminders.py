"""Per-item travel alarms stored with existing notes for offline compatibility."""
import re

PATTERN = re.compile(r"\[Align travel reminder: (\d{1,5}) minutes before\]")
EVENT_PATTERN = re.compile(r"\[Align event reminder: (\d{1,5}) minutes before\]")
INFO_PATTERN = re.compile(r"\[Align travel-info\][\s\S]*?\[/Align travel-info\]")
MAX_MINUTES = 10080  # 1 week

# Dropdown offsets for travel reminders and other Align calendar alerts.
ALERT_OFFSETS = (
    (5, '5 minutes'),
    (10, '10 minutes'),
    (15, '15 minutes'),
    (30, '30 minutes'),
    (45, '45 minutes'),
    (60, '1 hour'),
    (120, '2 hours'),
    (1440, '1 day'),
    (2880, '2 days'),
    (7200, '5 days'),
    (10080, '1 week'),
)


def _bounded(notes, pattern):
    match = pattern.search(notes or '')
    value = int(match.group(1)) if match else 0
    return value if 1 <= value <= MAX_MINUTES else None


def minutes(notes):
    return _bounded(notes, PATTERN)


def event_minutes(notes):
    return _bounded(notes, EVENT_PATTERN)


def with_guide(notes, leave_minutes=0, reminder_minutes=0, travel_info=''):
    """Store section travel text and the same reminder markers the calendar already reads."""
    text = INFO_PATTERN.sub('', notes or '')
    text = PATTERN.sub('', text)
    text = EVENT_PATTERN.sub('', text).strip()
    blocks = []
    info = str(travel_info or '').strip()[:500]
    if info:
        blocks.append(f'[Align travel-info]\n{info}\n[/Align travel-info]')
    if text:
        blocks.append(text)
    leave = int(leave_minutes or 0)
    reminder = int(reminder_minutes or 0)
    if leave:
        blocks.append(f'[Align travel reminder: {leave} minutes before]')
    if reminder:
        blocks.append(f'[Align event reminder: {reminder} minutes before]')
    return '\n'.join(blocks).strip()


def label(value):
    for minutes_before, text in ALERT_OFFSETS:
        if minutes_before == value:
            return f'{text} before'
    if not value:
        return 'At start'
    if value % 1440 == 0:
        days = value // 1440
        return f'{days} day{"s" if days != 1 else ""} before'
    if value % 60 == 0:
        hours = value // 60
        return f'{hours} hour{"s" if hours != 1 else ""} before'
    return f'{value} minutes before'


def rules(notes, existing=()):
    result = list(existing)
    value = minutes(notes)
    if value is not None:
        result = [r for r in result if r.get('title') != 'Time to Leave']
        result.append({'title': 'Time to leave (including walking)', 'minutes_before': value})
    reminder = event_minutes(notes)
    if reminder is not None and not any(
        item.get('title') == 'Reminder' and item.get('minutes_before') == reminder for item in result
    ):
        result.append({'title': 'Reminder', 'minutes_before': reminder})
    return result
