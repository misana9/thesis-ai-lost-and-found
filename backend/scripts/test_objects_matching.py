#!/usr/bin/env python3
"""Functional matching test using Objects/ photos through real FindIt scoring.

Simulates lost↔found matching with clip_service + compute_match:
  - Same-item pair (two photos of one object) should match
  - Different-item pair should score lower / often miss tier

Usage (from backend/):
  python scripts/test_objects_matching.py
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from clip_service import cosine_similarity, encode_image, encode_text  # noqa: E402
from matching import compute_match  # noqa: E402


def load_items(manifest: Path) -> dict[str, list[dict]]:
    by_item: dict[str, list[dict]] = defaultdict(list)
    with manifest.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            by_item[row["item_id"]].append(row)
    return by_item


def score_pair(
    *,
    lost_image: str | None,
    lost_text: str,
    found_image: str,
    found_text: str | None,
    lost_category: str,
    found_category: str,
) -> dict:
    lost_text_emb = encode_text(lost_text)
    found_img_emb = encode_image(found_image)
    lost_img_emb = encode_image(lost_image) if lost_image else None
    found_text_emb = encode_text(found_text) if found_text else None

    text_to_image = cosine_similarity(lost_text_emb, found_img_emb)
    image_to_image = (
        cosine_similarity(lost_img_emb, found_img_emb) if lost_img_emb is not None else None
    )
    found_text_to_lost_image = (
        cosine_similarity(found_text_emb, lost_img_emb)
        if found_text_emb is not None and lost_img_emb is not None
        else None
    )

    final, tier, same_cat, breakdown = compute_match(
        text_to_image=text_to_image,
        image_to_image=image_to_image,
        found_text_to_lost_image=found_text_to_lost_image,
        lost_category=lost_category,
        found_category=found_category,
    )
    return {
        "final_score": round(final, 4),
        "tier": tier,
        "same_category": same_cat,
        "breakdown": {k: (round(v, 4) if v is not None else None) for k, v in breakdown.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "dataset" / "manifest.csv",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--limit-items", type=int, default=0, help="0 = all items with >=2 images")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "dataset" / "objects_matching_functional.json",
    )
    args = parser.parse_args()
    rng = random.Random(args.seed)

    by_item = load_items(args.manifest)
    multi = sorted(
        [(iid, rows) for iid, rows in by_item.items() if len(rows) >= 2],
        key=lambda x: x[0],
    )
    if args.limit_items > 0:
        multi = multi[: args.limit_items]

    all_ids = list(by_item.keys())
    results = []
    same_hit = 0
    same_strong = 0
    wrong_suppressed = 0  # wrong item has no tier or lower than same-item
    n = 0

    print(f"Testing functional matching on {len(multi)} items (need >=2 photos each)...\n")

    for item_id, rows in multi:
        n += 1
        paths = [r["path"] for r in rows]
        cat = rows[0]["system_category"]
        stem = rows[0]["category_stem"].replace("_", " ")
        lost_img, found_img = rng.sample(paths, 2)
        lost_text = f"a photo of a {stem}"
        found_text = f"{stem}"

        same = score_pair(
            lost_image=lost_img,
            lost_text=lost_text,
            found_image=found_img,
            found_text=found_text,
            lost_category=cat,
            found_category=cat,
        )

        # hard-ish wrong: prefer another item in same stem/category if possible
        same_stem = [
            iid
            for iid in all_ids
            if iid != item_id and by_item[iid][0]["category_stem"] == rows[0]["category_stem"]
        ]
        pool = same_stem or [iid for iid in all_ids if iid != item_id]
        wrong_id = rng.choice(pool)
        wrong_rows = by_item[wrong_id]
        wrong_img = rng.choice(wrong_rows)["path"]
        wrong_cat = wrong_rows[0]["system_category"]
        wrong_stem = wrong_rows[0]["category_stem"].replace("_", " ")

        wrong = score_pair(
            lost_image=lost_img,
            lost_text=lost_text,
            found_image=wrong_img,
            found_text=wrong_stem,
            lost_category=cat,
            found_category=wrong_cat,
        )

        # text-only lost (no lost photo) vs correct found photo
        text_only = score_pair(
            lost_image=None,
            lost_text=lost_text,
            found_image=found_img,
            found_text=found_text,
            lost_category=cat,
            found_category=cat,
        )

        matched = same["tier"] is not None
        if matched:
            same_hit += 1
        if same["tier"] == "strong":
            same_strong += 1
        if (wrong["tier"] is None) or (same["final_score"] > wrong["final_score"]):
            wrong_suppressed += 1

        row = {
            "item_id": item_id,
            "wrong_item_id": wrong_id,
            "same_item": same,
            "wrong_item": wrong,
            "text_only_lost_vs_same_found": text_only,
            "same_beats_wrong": same["final_score"] > wrong["final_score"],
            "same_passes_threshold": matched,
        }
        results.append(row)

        print(
            f"{item_id:28} same={same['final_score']:.3f}/{same['tier'] or 'none':8} "
            f"wrong={wrong['final_score']:.3f}/{wrong['tier'] or 'none':8} "
            f"text-only={text_only['final_score']:.3f}/{text_only['tier'] or 'none':8} "
            f"{'OK' if same['final_score'] > wrong['final_score'] else 'FAIL'}"
        )

    summary = {
        "n_items_tested": n,
        "same_item_pass_rate": same_hit / n if n else 0.0,
        "same_item_strong_rate": same_strong / n if n else 0.0,
        "same_beats_wrong_rate": wrong_suppressed / n if n else 0.0,
        "thresholds": {"strong": 0.85, "possible": 0.70, "weak": 0.55},
    }
    payload = {"summary": summary, "results": results}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2))
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
