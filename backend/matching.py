from __future__ import annotations

from datetime import datetime
from difflib import SequenceMatcher


def adaptive_raw_score(
    text_to_image: float | None,
    image_to_image: float | None,
    found_text_to_lost_image: float | None,
) -> float:
    """Combine available similarity signals into a single raw score.

    Uses the low-magnitude cross-modal text-vs-image cosines rather than a direct
    description-to-description (text-to-text) term on purpose: text-to-text is a
    category-level signal (two different calculators both described "calculator"
    score ~1.0), so adding it floods results with same-category look-alikes. The
    cross-modal terms keep same-category clutter low while the image term drives
    same-item ranking.
    """
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
    final_score = raw_score * 1.10 if same_category else raw_score * 0.75
    return min(final_score, 0.99)


def score_tier(final_score: float) -> str | None:
    if final_score >= 0.85:
        return "strong"
    if final_score >= 0.70:
        return "possible"
    if final_score >= 0.55:
        return "weak"
    return None


def location_boost(lost_location: str | None, found_location: str | None) -> float:
    if not lost_location or not found_location:
        return 0.0
    a = lost_location.lower().strip()
    b = found_location.lower().strip()
    if not a or not b:
        return 0.0
    if a == b or a in b or b in a:
        return 0.04
    ratio = SequenceMatcher(None, a, b).ratio()
    if ratio >= 0.6:
        return 0.02
    lost_tokens = set(a.replace(",", " ").split())
    found_tokens = set(b.replace(",", " ").split())
    overlap = lost_tokens & found_tokens - {"floor", "near", "the", "a", "rm", "room"}
    if overlap:
        return 0.02
    return 0.0


def _parse_fuzzy_date(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    formats = (
        "%Y-%m-%d",
        "%B %d, %Y",
        "%b %d, %Y",
        "%m/%d/%Y",
        "%d/%m/%Y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def time_boost(lost_date: str | None, found_date: str | None) -> float:
    lost_dt = _parse_fuzzy_date(lost_date)
    found_dt = _parse_fuzzy_date(found_date)
    if not lost_dt or not found_dt:
        return 0.0
    delta_days = abs((lost_dt - found_dt).days)
    if delta_days == 0:
        return 0.03
    if delta_days <= 3:
        return 0.02
    if delta_days <= 7:
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
) -> tuple[float, str | None, bool, dict[str, float | None]]:
    # text_to_text is retained for the score breakdown (informational) but is not
    # fed into the score: it inflates same-category matches and floods results.
    raw_score = adaptive_raw_score(
        text_to_image, image_to_image, found_text_to_lost_image
    )
    same_category = lost_category == found_category
    final_score = apply_category_multiplier(raw_score, same_category)
    final_score = min(
        final_score
        + location_boost(lost_location, found_location)
        + time_boost(lost_date, found_date),
        0.99,
    )
    tier = score_tier(final_score)
    breakdown = {
        "text_to_image": text_to_image,
        "image_to_image": image_to_image,
        "found_text_to_lost_image": found_text_to_lost_image,
        "text_to_text": text_to_text,
    }
    return final_score, tier, same_category, breakdown
