"""User-facing calendar dates. Stored values and API payloads stay ISO."""
from __future__ import annotations

import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")


def format_display_date(value) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return f"{value.day:02d}/{value.month:02d}/{value.year:04d}"
    text = str(value).strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        try:
            parsed = date.fromisoformat(text[:10])
        except ValueError:
            return text
        return format_display_date(parsed)
    return text


def format_display_datetime(value) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(LONDON)
        return f"{format_display_date(value)} {value.hour:02d}:{value.minute:02d}"
    text = str(value).strip()
    if text.endswith("Z") or re.search(r"[+-]\d{2}:?\d{2}$", text):
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return format_display_date(text)
        return format_display_datetime(parsed)
    wall = re.match(r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})", text)
    if wall:
        year, month, day, hour, minute = wall.groups()
        return f"{day}/{month}/{year} {hour}:{minute}"
    return format_display_date(text)
