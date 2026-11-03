"""Per-item travel alarms stored with existing notes for offline compatibility."""
import re

PATTERN = re.compile(r"\[Align travel reminder: (\d{1,5}) minutes before\]")
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


def minutes(notes):
    match = PATTERN.search(notes or '')
    value = int(match.group(1)) if match else 0
    return value if 1 <= value <= MAX_MINUTES else None


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
    return result
