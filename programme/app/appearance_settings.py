"""Shared appearance defaults and per-account override validation."""
from __future__ import annotations

import re


DEFAULT_APPEARANCE = {
    "colors": {
        "accent": "#365ce6",
        "canvas": "#f7f8fc",
        "surface": "#ffffff",
        "text": "#162147",
    },
    "banners": {
        "today": "#172a62",
        "upcoming": "#365ce6",
        "annual_leave": "#0f9d8a",
        "section_detail": "#365ce6",
    },
    "events": {
        "style": "standard",
        "density": "comfortable",
        "accent": "#6577bd",
        "location_banner": "on",
        "time_place": "left",
        "time_size": "large",
        "title_format": "location_area",
    },
    "type": {
        "scale": "default",
        "corners": "soft",
        "font": "system",
        "heading": "bold",
        "theme": "light",
    },
    "calendar": {
        "month_cell": "#f1f5fd",
        "month_weekend": "#e9eefb",
        "month_date_band": "#dfe7fb",
        "list_day": "#f1f5fd",
        "list_day_header": "#edf2ff",
        "today_cell": "#e4ecff",
        "week_headings": "show",
    },
}

DEFAULT_PERMISSIONS = {
    "colors": False,
    "banners": False,
    "events": False,
    "type": False,
    "calendar": False,
}

COLOR_KEYS = {
    "colors": frozenset(DEFAULT_APPEARANCE["colors"]),
    "banners": frozenset(DEFAULT_APPEARANCE["banners"]),
    "events": frozenset({"accent"}),
    "calendar": frozenset(DEFAULT_APPEARANCE["calendar"]) - {"week_headings"},
}


def _color(value: object, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise ValueError(f"Choose a valid six-digit hex colour for {label}.")
    return value.lower()


def validate_appearance(value: object) -> dict:
    if not isinstance(value, dict):
        raise ValueError("Appearance settings must be an object.")
    extra = set(value) - set(DEFAULT_APPEARANCE)
    if extra:
        raise ValueError("Appearance settings contain unsupported categories.")

    result = {
        category: dict(defaults)
        for category, defaults in DEFAULT_APPEARANCE.items()
    }
    for category, supplied in value.items():
        if not isinstance(supplied, dict):
            raise ValueError(f"{category.title()} settings must be an object.")
        defaults = DEFAULT_APPEARANCE[category]
        if set(supplied) - set(defaults):
            raise ValueError(f"{category.title()} settings contain unsupported options.")
        for key, item in supplied.items():
            if category in COLOR_KEYS and key in COLOR_KEYS[category]:
                result[category][key] = _color(item, key.replace("_", " "))
            elif category == "events" and key == "style":
                if not isinstance(item, str) or item not in {"standard", "compact", "tinted"}:
                    raise ValueError("Choose a supported event style.")
                result[category][key] = item
            elif category == "events" and key == "density":
                if not isinstance(item, str) or item not in {"comfortable", "compact"}:
                    raise ValueError("Choose a supported event spacing.")
                result[category][key] = item
            elif category == "events" and key == "location_banner":
                if not isinstance(item, str) or item not in {"on", "off"}:
                    raise ValueError("Choose whether same-location events share a banner.")
                result[category][key] = item
            elif category == "events" and key == "time_place":
                if not isinstance(item, str) or item not in {"left", "right"}:
                    raise ValueError("Choose where the event time sits.")
                result[category][key] = item
            elif category == "events" and key == "time_size":
                if not isinstance(item, str) or item not in {"large", "standard"}:
                    raise ValueError("Choose an event time size.")
                result[category][key] = item
            elif category == "events" and key == "title_format":
                if not isinstance(item, str) or item not in {"location_area", "area"}:
                    raise ValueError("Choose an event title format.")
                result[category][key] = item
            elif category == "type" and key == "scale":
                if not isinstance(item, str) or item not in {"default", "large"}:
                    raise ValueError("Choose a supported text size.")
                result[category][key] = item
            elif category == "type" and key == "corners":
                if not isinstance(item, str) or item not in {"soft", "square"}:
                    raise ValueError("Choose a supported corner style.")
                result[category][key] = item
            elif category == "type" and key == "font":
                if not isinstance(item, str) or item not in {"system", "serif", "rounded", "mono"}:
                    raise ValueError("Choose a supported font style.")
                result[category][key] = item
            elif category == "type" and key == "theme":
                if not isinstance(item, str) or item not in {"light", "dark", "auto"}:
                    raise ValueError("Choose a supported colour theme.")
                result[category][key] = item
            elif category == "type" and key == "heading":
                if not isinstance(item, str) or item not in {"normal", "bold"}:
                    raise ValueError("Choose a supported heading weight.")
                result[category][key] = item
            elif category == "calendar" and key == "week_headings":
                if not isinstance(item, str) or item not in {"show", "hide"}:
                    raise ValueError("Choose whether to show week headings.")
                result[category][key] = item
            else:
                raise ValueError(f"Unsupported {category} option.")
    return result


def validate_permissions(value: object) -> dict:
    if not isinstance(value, dict) or set(value) - set(DEFAULT_PERMISSIONS):
        raise ValueError("Choose which supported appearance settings users may change.")
    if any(not isinstance(enabled, bool) for enabled in value.values()):
        raise ValueError("User appearance permissions must be enabled or disabled.")
    return {**DEFAULT_PERMISSIONS, **value}


def validate_user_overrides(value: object, permissions: dict) -> dict:
    if not isinstance(value, dict) or set(value) - set(DEFAULT_APPEARANCE):
        raise ValueError("Personal appearance settings contain unsupported categories.")
    result = {}
    for category, supplied in value.items():
        if not permissions.get(category, False):
            raise ValueError(f"{category.title()} customisation is not enabled for your account.")
        if not isinstance(supplied, dict):
            raise ValueError(f"{category.title()} settings must be an object.")
        if category not in {"events", "type", "colors", "banners", "calendar"}:
            raise ValueError("Unsupported appearance category.")
        normalized = validate_appearance({category: supplied})[category]
        result[category] = {key: normalized[key] for key in supplied}
    return result


def resolve_appearance(shared: object, personal: object, permissions: object) -> dict:
    effective = validate_appearance(shared)
    enabled = validate_permissions(permissions)
    if not isinstance(personal, dict):
        raise ValueError("Saved personal appearance settings are invalid.")
    permitted = {key: value for key, value in personal.items() if enabled.get(key, False)}
    personal = validate_user_overrides(permitted, enabled) if permitted else {}
    for category, values in personal.items():
        effective[category].update(values)
    return effective
