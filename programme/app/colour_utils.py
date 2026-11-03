"""Shared validation helpers for retained V3 UI and organiser fields."""
import re


def colour(value):
    value = str(value)
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
        raise ValueError('Choose a valid colour (for example #365CE6).')
    return value.upper()
