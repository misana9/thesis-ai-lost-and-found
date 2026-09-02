from __future__ import annotations

from datetime import datetime
from difflib import SequenceMatcher

from locations import LOCATION_SET, parse_locations

# soft boost when found spot is in the lost places list
LOCATION_MATCH_BOOST = 0.06


def normalize_serial(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = "".join(ch for ch in str(value).upper() if ch.isalnum())
    return cleaned or None


def compare_serials(lost_serial: str | None, found_serial: str | None) -> str:
    """Staff verification flag only — never used to auto-claim or score CLIP."""
    lost = normalize_serial(lost_serial)
    found = normalize_serial(found_serial)
    if not lost and not found:
        return "missing"
    if not lost or not found:
        return "one_sided"
    if lost == found:
        return "match"
    shorter, longer = (lost, found) if len(lost) <= len(found) else (found, lost)
    # IMEI / serial typed with a prefix ("IMEI …") still counts as the same identifier
    if len(shorter) >= 8 and shorter in longer:
        return "match"
    if len(lost) >= 4 and len(found) >= 4 and (lost[-4:] == found[-4:] or lost in found or found in lost):
        return "partial"
    return "mismatch"


def adaptive_raw_score(
    text_to_image: float | None,
    image_to_image: float | None,
    found_text_to_lost_image: float | None,
) -> float:
    # skip text↔text on purpose — two different calculators both described
    # as "calculator" score ~1.0 and flood the ranking with same-category junk
    if image_to_image is not None and text_to_image is not None:
        base = image_to_image * 0.60 + text_to_image * 0.25
        if found_text_to_lost_image is not None:
            return base + found_text_to_lost_image * 0.15
        return image_to_image * 0.75 + text_to_image * 0.25
    if image_to_image is not None:
        if found_text_to_lost_image is not None:
            return image_to_image * 0.85 + found_text_to_lost_image * 0.15
        return image_to_image
    return float(text_to_image or 0.0)


def apply_category_multiplier(raw_score: float, same_category: bool) -> float:
    final = raw_score * 1.10 if same_category else raw_score * 0.75
    return min(final, 0.99)


def score_tier(final_score: float) -> str | None:
    if final_score >= 0.85:
        return "strong"
    if final_score >= 0.70:
        return "possible"
    if final_score >= 0.55:
        return "weak"
    return None


def locations_overlap(lost_location: str | None, found_location: str | None) -> bool:
    lost_set = set(parse_locations(lost_location))
    found_set = set(parse_locations(found_location))
    if not lost_set or not found_set:
        return False
    return bool(lost_set & found_set)


def location_boost(
    lost_location: str | None,
    found_location: str | None,
    *,
    apply_boost: bool = True,
) -> float:
    # soft prior only — apply_boost=False for "search all locations"
    if not apply_boost or not lost_location or not found_location:
        return 0.0

    lost_list = parse_locations(lost_location)
    found_list = parse_locations(found_location)
    if not lost_list or not found_list:
        return 0.0

    # dropdown labels from CAMPUS_LOCATIONS
    lost_known = {n for n in lost_list if n in LOCATION_SET}
    found_known = {n for n in found_list if n in LOCATION_SET}
    if lost_known and found_known:
        return LOCATION_MATCH_BOOST if (lost_known & found_known) else 0.0

    # older free-text rows still get a light fuzzy bump
    a = lost_location.lower().strip()
    b = found_location.lower().strip()
    if a == b or a in b or b in a:
        return 0.04
    if SequenceMatcher(None, a, b).ratio() >= 0.6:
        return 0.02
    lost_tokens = set(a.replace(",", " ").replace("|", " ").split())
    found_tokens = set(b.replace(",", " ").replace("|", " ").split())
    overlap = lost_tokens & found_tokens - {"floor", "near", "the", "a", "rm", "room"}
    if overlap:
        return 0.02
    return 0.0


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def time_boost(lost_date: str | None, found_date: str | None) -> float:
    lost_dt = _parse_date(lost_date)
    found_dt = _parse_date(found_date)
    if not lost_dt or not found_dt:
        return 0.0
    days = abs((lost_dt - found_dt).days)
    if days == 0:
        return 0.03
    if days <= 3:
        return 0.02
    if days <= 7:
        return 0.01
    return 0.0


def compute_match(
    *,
    text_to_image: float | None,
    image_to_image: float | None,
    found_text_to_lost_image: float | None,
    text_to_text: float | None = None,
    lost_category: str,
    found_category: str,
    lost_location: str | None = None,
    found_location: str | None = None,
    lost_date: str | None = None,
    found_date: str | None = None,
    apply_location_boost: bool = True,
) -> tuple[float, str | None, bool, dict[str, float | None]]:
    # text_to_text stays in the breakdown for the UI but is not scored
    raw = adaptive_raw_score(text_to_image, image_to_image, found_text_to_lost_image)
    same_cat = lost_category == found_category
    score = apply_category_multiplier(raw, same_cat)
    score = min(
        score
        + location_boost(lost_location, found_location, apply_boost=apply_location_boost)
        + time_boost(lost_date, found_date),
        0.99,
    )
    return score, score_tier(score), same_cat, {
        "text_to_image": text_to_image,
        "image_to_image": image_to_image,
        "found_text_to_lost_image": found_text_to_lost_image,
        "text_to_text": text_to_text,
    }
