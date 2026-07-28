#!/usr/bin/env python3
# synthetic Precision@1 / Recall@3 / MRR eval — run from backend/: python scripts/run_eval.py

from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from matching import compute_match


def make_pair(seed: int, category: str, shared: float) -> tuple[dict, dict]:
    rng = random.Random(seed)
    lost = {
        "category": category,
        "location": f"Building {seed % 5}",
        "date": f"2026-06-{(seed % 20) + 1:02d}",
        "text_to_image": shared + rng.uniform(-0.03, 0.03),
        "image_to_image": shared + rng.uniform(-0.02, 0.02),
        "found_text_to_lost_image": shared + rng.uniform(-0.04, 0.02),
    }
    found = {
        "id": f"gt-{seed}",
        "category": category,
        "location": lost["location"],
        "date_found": lost["date"],
        "signals": {
            "text_to_image": min(0.98, max(0.4, lost["text_to_image"])),
            "image_to_image": min(0.98, max(0.4, lost["image_to_image"])),
            "found_text_to_lost_image": min(0.98, max(0.35, lost["found_text_to_lost_image"])),
        },
    }
    return lost, found


def distractor(seed: int, lost_category: str) -> dict:
    rng = random.Random(seed + 999)
    cats = ["Gadgets", "Electronics", "Clothing", "Umbrella", "Wallet / Purse", "Other"]
    category = rng.choice([c for c in cats if c != lost_category] or cats)
    low = rng.uniform(0.35, 0.62)
    return {
        "id": f"d-{seed}",
        "category": category,
        "location": f"Hall {rng.randint(1, 9)}",
        "date_found": f"2026-05-{(seed % 28) + 1:02d}",
        "signals": {
            "text_to_image": low,
            "image_to_image": low - 0.05,
            "found_text_to_lost_image": low - 0.08,
        },
    }


def rank_query(lost: dict, candidates: list[dict]) -> list[dict]:
    ranked = []
    for candidate in candidates:
        score, tier, same, _ = compute_match(
            text_to_image=candidate["signals"]["text_to_image"],
            image_to_image=candidate["signals"]["image_to_image"],
            found_text_to_lost_image=candidate["signals"]["found_text_to_lost_image"],
            lost_category=lost["category"],
            found_category=candidate["category"],
            lost_location=lost["location"],
            found_location=candidate["location"],
            lost_date=lost["date"],
            found_date=candidate["date_found"],
        )
        if tier is None:
            continue
        ranked.append({"id": candidate["id"], "score": score, "same_category": same, "tier": tier})
    ranked.sort(key=lambda row: row["score"], reverse=True)
    return ranked


def main() -> None:
    categories = [
        "Backpack / Bag",
        "Gadgets",
        "Gadget Accessories",
        "Electronics",
        "Water Bottle",
        "Glasses",
        "Wallet / Purse",
        "Clothing",
        "Umbrella",
        "Other",
    ]
    p_at_1 = 0
    recall_at_3 = 0
    mrr = 0.0
    n = 40

    for i in range(n):
        category = categories[i % len(categories)]
        lost, truth = make_pair(i, category, shared=0.86)
        candidates = [truth] + [distractor(i * 10 + j, category) for j in range(8)]
        random.Random(i).shuffle(candidates)
        ranked = rank_query(lost, candidates)
        ids = [row["id"] for row in ranked]
        if ids and ids[0] == truth["id"]:
            p_at_1 += 1
        if truth["id"] in ids[:3]:
            recall_at_3 += 1
        if truth["id"] in ids:
            mrr += 1.0 / (ids.index(truth["id"]) + 1)

    print("AMAlost matching evaluation (synthetic CLIP-like signals)")
    print(f"Queries: {n}")
    print(f"Precision@1: {p_at_1 / n:.3f}")
    print(f"Recall@3:    {recall_at_3 / n:.3f}")
    print(f"MRR:         {mrr / n:.3f}")


if __name__ == "__main__":
    main()
