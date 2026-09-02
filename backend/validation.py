from __future__ import annotations

import re

MIN_DESCRIPTION_CHARS = 8
MIN_DESCRIPTION_TOKENS = 2

# these alone don't identify a real item
VAGUE_DESCRIPTIONS = {
    "item",
    "items",
    "thing",
    "things",
    "stuff",
    "object",
    "objects",
    "lost",
    "found",
    "something",
    "someone",
    "misc",
    "miscellaneous",
    "n/a",
    "na",
    "none",
    "test",
    "asdf",
    "xxx",
}


def normalize_description(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.strip())


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def validate_item_description(description: str | None, *, required: bool = True) -> str:
    cleaned = normalize_description(description)
    if not cleaned:
        if required:
            raise ValueError(
                "Please add a short description of the item "
                "(color, brand, marks, or other distinctive details)."
            )
        return ""

    tokens = _tokens(cleaned)
    if len(cleaned) < MIN_DESCRIPTION_CHARS or len(tokens) < MIN_DESCRIPTION_TOKENS:
        raise ValueError(
            "Description is too short. Include at least a couple of details "
            "(color, brand, or distinctive marks)."
        )

    meaningful = [t for t in tokens if t not in VAGUE_DESCRIPTIONS]
    if not meaningful:
        raise ValueError(
            "Description is too vague. Add distinctive details so matching can work "
            "(color, brand, model, scratches, stickers, etc.)."
        )

    # e.g. "item item item"
    if set(tokens) <= VAGUE_DESCRIPTIONS:
        raise ValueError(
            "Description is too vague. Add distinctive details so matching can work "
            "(color, brand, model, scratches, stickers, etc.)."
        )

    return cleaned
