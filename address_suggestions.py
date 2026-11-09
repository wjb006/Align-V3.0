"""Formatting and conservative deduplication for address search results."""
import math
import re


def address_label(name, street, postcode, locality, *extra):
    parts = []
    for value in (name, street, postcode, locality, *extra):
        value = str(value or "").strip()
        if value and value.casefold() not in {part.casefold() for part in parts}:
            parts.append(value)
    return ", ".join(parts)


def here_label(item):
    label = str((item.get("address") or {}).get("label") or item.get("title") or "").strip()
    title = str(item.get("title") or "").strip()
    components = [" ".join(part.split()).casefold() for part in label.split(",")]
    title_components = [" ".join(part.split()).casefold() for part in title.split(",")]
    title_in_label = any(components[index:index + len(title_components)] == title_components
                         for index in range(len(components)))
    if item.get("resultType") == "place" and title and not title_in_label:
        return f"{title}, {label}"
    return label


def deduplicate(results, *, label_key="label", point_key=None):
    """Keep the first matching label at a nearby point, without merging distinct places."""
    kept = []
    for result in results:
        label = re.sub(r"\s+", " ", str(result.get(label_key) or "").strip()).casefold()
        point = result.get(point_key) if point_key else (result.get("latitude"), result.get("longitude"))
        try:
            lat, lon = (float(value) for value in point)
            if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError("Invalid coordinates")
        except (TypeError, ValueError):
            lat, lon = None, None
        duplicate = False
        for existing_label, existing_lat, existing_lon in (
            (entry[1], entry[2], entry[3]) for entry in kept
        ):
            if label != existing_label or lat is None or existing_lat is None:
                continue
            lat_delta = math.radians(lat - existing_lat)
            lon_delta = math.radians(lon - existing_lon)
            haversine = math.sin(lat_delta / 2) ** 2 + math.cos(math.radians(lat)) * math.cos(math.radians(existing_lat)) * math.sin(lon_delta / 2) ** 2
            if 2 * 6371000 * math.asin(math.sqrt(min(1, haversine))) <= 50:
                duplicate = True
                break
        if not duplicate:
            kept.append((result, label, lat, lon))
    return [entry[0] for entry in kept]
