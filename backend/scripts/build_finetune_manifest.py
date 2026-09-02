#!/usr/bin/env python3
"""Scan Objects/ into a fine-tune manifest (train/val/test by item_id).

Usage (from backend/):
  python scripts/build_finetune_manifest.py
  python scripts/build_finetune_manifest.py --objects ../Objects --out ../dataset
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
SKIP_TOP = {"objects2", "sports"}

# Map Objects folder stem -> FindIt system category
CATEGORY_MAP = {
    "phone": "Gadgets",
    "ipad": "Gadgets",
    "laptop": "Gadgets",
    "earphone": "Gadget Accessories",
    "powerbank": "Gadget Accessories",
    "adapter": "Gadget Accessories",
    "charger": "Gadget Accessories",
    "cable": "Gadget Accessories",
    "mouse": "Gadget Accessories",
    "usb": "Gadget Accessories",
    "minifan": "Electronics",
    "calculator": "School Supplies",
    "pen": "School Supplies",
    "ballpen": "School Supplies",
    "notebook": "School Supplies",
    "id": "Other",
    "key": "Other",  # no dedicated Keys category in current FindIt list
    "wallet": "Wallet / Purse",
    "tumbler": "Water Bottle",
    "bag": "Backpack / Bag",
    "sanitizer": "Other",
    "umbrella": "Umbrella",
    "glasses": "Glasses",
    "clothing": "Clothing",
}


def _fix_category_map(valid_categories: list[str]) -> dict[str, str]:
    mapping = dict(CATEGORY_MAP)
    if "Keys" in valid_categories:
        mapping["key"] = "Keys"
    return mapping


def stem_from_top(name: str) -> str:
    return name.rstrip("-").lower()


def discover_items(objects_dir: Path) -> list[dict]:
    items: list[dict] = []
    for top in sorted(objects_dir.iterdir()):
        if not top.is_dir():
            continue
        if top.name.startswith(".") or top.name.lower() in SKIP_TOP:
            continue
        stem = stem_from_top(top.name)
        for inst in sorted(top.iterdir()):
            if not inst.is_dir() or inst.name.startswith("."):
                continue
            images = [
                p
                for p in inst.rglob("*")
                if p.is_file() and p.suffix.lower() in IMAGE_EXTS and not p.name.startswith(".")
            ]
            if not images:
                continue
            item_id = f"{stem}_{inst.name}"
            items.append(
                {
                    "item_id": item_id,
                    "category_stem": stem,
                    "instance_dir": str(inst.resolve()),
                    "images": [str(p.resolve()) for p in sorted(images)],
                    "n_images": len(images),
                }
            )
    return items


def assign_splits(
    items: list[dict],
    *,
    seed: int,
    min_train_images: int,
    val_ratio: float,
    test_ratio: float,
) -> dict[str, str]:
    """Split by item_id. Items with too few images can still be test-only gallery."""
    rng = random.Random(seed)
    eligible = [it for it in items if it["n_images"] >= min_train_images]
    thin = [it for it in items if it["n_images"] < min_train_images]

    rng.shuffle(eligible)
    n = len(eligible)
    n_test = max(1, int(round(n * test_ratio))) if n >= 5 else (1 if n >= 2 else 0)
    n_val = max(1, int(round(n * val_ratio))) if n - n_test >= 4 else 0
    # Ensure train gets the rest
    while n_test + n_val >= n and n_test > 0:
        n_test -= 1
    while n_test + n_val >= n and n_val > 0:
        n_val -= 1

    splits: dict[str, str] = {}
    test_items = eligible[:n_test]
    val_items = eligible[n_test : n_test + n_val]
    train_items = eligible[n_test + n_val :]

    for it in train_items:
        splits[it["item_id"]] = "train"
    for it in val_items:
        splits[it["item_id"]] = "val"
    for it in test_items:
        splits[it["item_id"]] = "test"
    # Thin items: keep out of train (use as extra test distractors if >=1 image)
    for it in thin:
        splits[it["item_id"]] = "test"

    return splits


def main() -> None:
    parser = argparse.ArgumentParser(description="Build fine-tune manifest from Objects/")
    parser.add_argument(
        "--objects",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "Objects",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "dataset",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-train-images", type=int, default=2)
    parser.add_argument("--val-ratio", type=float, default=0.10,
                        help="Fraction of eligible items for validation (with test_ratio, held-out ≈ 20%%)")
    parser.add_argument("--test-ratio", type=float, default=0.10,
                        help="Fraction of eligible items for final test (train ≈ 80%%)")
    args = parser.parse_args()

    try:
        from categories import CATEGORIES
    except ImportError:
        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from categories import CATEGORIES

    cat_map = _fix_category_map(CATEGORIES)
    objects_dir = args.objects.resolve()
    out_dir = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    items = discover_items(objects_dir)
    if not items:
        raise SystemExit(f"No labeled item folders with images found under {objects_dir}")

    splits = assign_splits(
        items,
        seed=args.seed,
        min_train_images=args.min_train_images,
        val_ratio=args.val_ratio,
        test_ratio=args.test_ratio,
    )

    rows: list[dict] = []
    for it in items:
        system_cat = cat_map.get(it["category_stem"], "Other")
        split = splits[it["item_id"]]
        for img in it["images"]:
            rows.append(
                {
                    "path": img,
                    "item_id": it["item_id"],
                    "category_stem": it["category_stem"],
                    "system_category": system_cat,
                    "split": split,
                }
            )

    manifest_csv = out_dir / "manifest.csv"
    with manifest_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["path", "item_id", "category_stem", "system_category", "split"],
        )
        writer.writeheader()
        writer.writerows(rows)

    by_split: dict[str, set[str]] = defaultdict(set)
    imgs_by_split: dict[str, int] = defaultdict(int)
    for row in rows:
        by_split[row["split"]].add(row["item_id"])
        imgs_by_split[row["split"]] += 1

    summary = {
        "objects_dir": str(objects_dir),
        "n_images": len(rows),
        "n_items": len(items),
        "items_by_split": {k: len(v) for k, v in sorted(by_split.items())},
        "images_by_split": dict(sorted(imgs_by_split.items())),
        "item_ids_by_split": {k: sorted(v) for k, v in sorted(by_split.items())},
        "skipped_note": (
            "Empty instance folders are ignored. "
            "Items with fewer than min-train-images are forced into test."
        ),
        "seed": args.seed,
        "min_train_images": args.min_train_images,
    }
    summary_path = out_dir / "manifest_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Wrote {manifest_csv}")
    print(f"Wrote {summary_path}")
    print(json.dumps({k: summary[k] for k in ('n_images', 'n_items', 'items_by_split', 'images_by_split')}, indent=2))


if __name__ == "__main__":
    main()
