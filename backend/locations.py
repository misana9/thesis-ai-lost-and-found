# Found = one discovery spot. Lost = one or more places visited that day.

CAMPUS_LOCATIONS = [
    "Registrar Office",
    "Faculty",
    "Library",
    "Room 401",
    "Room 402",
    "Room 403",
    "Room 404",
    "Room 405",
    "Room 406",
    "Room 407",
    "Room 408",
    "Room 409",
    "Room 410",
]

LOCATION_SET = set(CAMPUS_LOCATIONS)
LOCATION_JOIN = " | "


def parse_locations(value: str | None) -> list[str]:
    if not value:
        return []
    parts = []
    for raw in value.replace(",", "|").split("|"):
        name = raw.strip()
        if name:
            parts.append(name)
    seen = set()
    ordered = []
    for name in parts:
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


def format_locations(locations: list[str]) -> str:
    return LOCATION_JOIN.join(locations)


def validate_found_location(value: str | None) -> str:
    name = (value or "").strip()
    if not name:
        raise ValueError("Please select where the item was found.")
    if name not in LOCATION_SET:
        raise ValueError(
            f"Invalid found location. Choose one of: {', '.join(CAMPUS_LOCATIONS)}"
        )
    return name


def validate_lost_locations(value: str | None) -> str:
    names = parse_locations(value)
    if not names:
        raise ValueError(
            "Select at least one place you visited the day the item was lost."
        )
    invalid = [n for n in names if n not in LOCATION_SET]
    if invalid:
        raise ValueError(
            f"Invalid location(s): {', '.join(invalid)}. "
            f"Choose from: {', '.join(CAMPUS_LOCATIONS)}"
        )
    # keep CAMPUS_LOCATIONS order for consistent storage
    ordered = [loc for loc in CAMPUS_LOCATIONS if loc in set(names)]
    return format_locations(ordered)
