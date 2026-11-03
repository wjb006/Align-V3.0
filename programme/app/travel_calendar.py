"""Turns a saved event journey plan into calendar travel data."""
import re
from datetime import datetime, timedelta

LEAVE = re.compile(
    r"Leave (?:home|current location): (\d{1,2}) ([A-Za-z]{3}) (\d{1,2}):(\d{2})"
)
LEAVE_DMY = re.compile(
    r"Leave(?: [^:\n]{0,80})?: (\d{1,2})/(\d{1,2})/(\d{4}) (\d{1,2}):(\d{2})"
)
LEAVE_SHORT = re.compile(r"Leave(?: home| current location)?: (\d{1,2}):(\d{2})")
ARRIVE = re.compile(r"Arrive(?: at event location)?: (\d{1,2}):(\d{2})")
TRAVEL = re.compile(r"approximately (\d{1,4}) minutes travelling")
TRANSIT = re.compile(
    r"^(Bus|Train|Ferry|Tram|Metro|Underground|Service)\s+(\S+)(?:\s+towards\s+([^·]+))?"
    r"(?:.*?(\d{1,2}:\d{2}))?",
    re.I | re.M,
)
MAX_LEAD = timedelta(hours=12)


def plan(notes, start):
    """Return (leave_at, travel_minutes) for a saved journey, or None."""
    text = notes or ""
    numeric = LEAVE_DMY.search(text)
    if numeric:
        candidate = datetime(int(numeric[3]), int(numeric[2]), int(numeric[1]), int(numeric[4]), int(numeric[5]))
        if candidate <= start and start - candidate <= MAX_LEAD:
            travel = TRAVEL.search(text)
            minutes = int(travel[1]) if travel else max(1, int((start - candidate).total_seconds() // 60))
            return candidate, minutes
        return None
    match = LEAVE.search(text)
    best = None
    if match:
        for year in (start.year - 1, start.year, start.year + 1):
            try:
                candidate = datetime.strptime(
                    f"{match[1]} {match[2]} {year} {match[3]}:{match[4]}", "%d %b %Y %H:%M")
            except ValueError:
                return None
            if candidate <= start and (best is None or candidate > best):
                best = candidate
    else:
        short = LEAVE_SHORT.search(text)
        if short:
            candidate = start.replace(hour=int(short[1]), minute=int(short[2]), second=0, microsecond=0)
            if candidate <= start:
                best = candidate
    if best is None or start - best > MAX_LEAD:
        return None
    travel = TRAVEL.search(text)
    minutes = int(travel[1]) if travel else max(1, int((start - best).total_seconds() // 60))
    return best, minutes


def leave_alert_title(leave_at, event_name):
    """iCloud / calendar alert wording for time-to-leave."""
    name = (event_name or 'Event').strip() or 'Event'
    return f'Leave at {leave_at.strftime("%H:%M")} for "{name}"'


def _transit_lines(text):
    lines = []
    for match in TRANSIT.finditer(text or ''):
        vehicle, service, towards, depart = match.group(1), match.group(2), (match.group(3) or '').strip(), match.group(4)
        label = f"{vehicle} {service}"
        if towards:
            # Prefer a short place name from the headsign (first token / phrase).
            label = f"{label} {towards.split()[0]}"
        if depart:
            lines.append(f"{depart} {label}")
        else:
            lines.append(label)
    return lines


def calendar_description(notes, fallback='Scheduled in Align'):
    """Format Align notes for iCloud DESCRIPTION with a clear travel summary."""
    text = notes or ''
    numeric = LEAVE_DMY.search(text)
    leave = None if numeric else (LEAVE.search(text) or LEAVE_SHORT.search(text))
    arrive = ARRIVE.search(text)
    transit = _transit_lines(text)
    if not numeric and not leave and not arrive and not transit:
        return text.strip() or fallback
    bullets = []
    if numeric:
        bullets.append(f"- Leave: {int(numeric.group(4)):02d}:{int(numeric.group(5)):02d}")
    elif leave:
        # Full Leave home match has time in groups 3-4; short match uses 1-2.
        if leave.re is LEAVE:
            bullets.append(f"- Leave: {leave.group(3)}:{leave.group(4)}")
        else:
            bullets.append(f"- Leave: {leave.group(1)}:{leave.group(2)}")
    for item in transit[:4]:
        bullets.append(f"- Bus/train: {item}")
    if arrive:
        bullets.append(f"- Arrive: {arrive.group(1)}:{arrive.group(2)}")
    # Keep any free-form notes outside the Align travel block.
    remainder = re.sub(r"\[Align travel\][\s\S]*?\[/Align travel\]", '', text)
    remainder = re.sub(r"\[Align travel steps\][\s\S]*?\[/Align travel steps\]", '', remainder)
    remainder = re.sub(r"\[Align travel reminder: \d{1,5} minutes before\]", '', remainder)
    remainder = remainder.strip()
    if remainder:
        bullets.append('')
        bullets.append(remainder)
    return '\n'.join(bullets).strip() or fallback
