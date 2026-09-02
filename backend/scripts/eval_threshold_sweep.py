#!/usr/bin/env python3
"""Sweep final-score thresholds to justify Strong/Possible/Weak tiers.

Builds same-item (positive) and different-item (negative) pairs from the
Objects manifest, scores them with compute_match, then reports precision,
recall, and false-positive rate at each threshold.

Usage (from backend/):
  python scripts/eval_threshold_sweep.py
  python scripts/eval_threshold_sweep.py --split test --out ../dataset/threshold_sweep.json
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

DEFAULT_THRESHOLDS = [
    0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90,
]
TIER_CUTOFFS = {"weak": 0.55, "possible": 0.70, "strong": 0.85}


def load_by_item(manifest: Path, split: str | None) -> dict[str, list[dict]]:
    by_item: dict[str, list[dict]] = defaultdict(list)
    with manifest.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if split and row["split"] != split:
                continue
            by_item[row["item_id"]].append(row)
    return by_item


def score_pair(lost_img: str, found_img: str, lost_text: str, found_text: str,
               lost_cat: str, found_cat: str) -> float:
    lost_text_emb = encode_text(lost_text)
    found_img_emb = encode_image(found_img)
    lost_img_emb = encode_image(lost_img)
    found_text_emb = encode_text(found_text)
    final, _, _, _ = compute_match(
        text_to_image=cosine_similarity(lost_text_emb, found_img_emb),
        image_to_image=cosine_similarity(lost_img_emb, found_img_emb),
        found_text_to_lost_image=cosine_similarity(found_text_emb, lost_img_emb),
        lost_category=lost_cat,
        found_category=found_cat,
    )
    return float(final)


def build_labeled_scores(by_item: dict[str, list[dict]], seed: int) -> list[dict]:
    rng = random.Random(seed)
    item_ids = [i for i, rows in by_item.items() if len(rows) >= 2]
    labeled: list[dict] = []

    for item_id in item_ids:
        rows = by_item[item_id]
        a, b = rng.sample(rows, 2)
        stem = a["category_stem"].replace("_", " ")
        cat = a["system_category"]
        lost_text = f"a photo of a {stem}"
        found_text = f"found {stem}"
        score = score_pair(a["path"], b["path"], lost_text, found_text, cat, cat)
        labeled.append({"label": 1, "score": score, "item_id": item_id, "kind": "same_item"})

        others = [i for i in item_ids if i != item_id]
        if not others:
            continue
        # Prefer hard negative in same category stem when available
        same_stem = [
            i for i in others
            if by_item[i][0]["category_stem"] == a["category_stem"]
        ]
        neg_id = rng.choice(same_stem or others)
        neg = rng.choice(by_item[neg_id])
        neg_cat = neg["system_category"]
        neg_stem = neg["category_stem"].replace("_", " ")
        score_neg = score_pair(
            a["path"], neg["path"], lost_text, f"found {neg_stem}", cat, neg_cat
        )
        labeled.append({
            "label": 0,
            "score": score_neg,
            "item_id": item_id,
            "neg_item_id": neg_id,
            "kind": "different_item",
        })
    return labeled


def metrics_at(labeled: list[dict], threshold: float) -> dict:
    tp = fp = tn = fn = 0
    for row in labeled:
        pred = row["score"] >= threshold
        if pred and row["label"] == 1:
            tp += 1
        elif pred and row["label"] == 0:
            fp += 1
        elif (not pred) and row["label"] == 0:
            tn += 1
        else:
            fn += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "threshold": threshold,
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "fpr": round(fpr, 4),
        "f1": round(f1, 4),
        "n_pos": tp + fn,
        "n_neg": fp + tn,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "dataset" / "manifest.csv",
    )
    parser.add_argument("--split", type=str, default=None,
                        help="Optional split filter (train/val/test). Default: all rows.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "dataset" / "threshold_sweep.json",
    )
    args = parser.parse_args()

    by_item = load_by_item(args.manifest, args.split)
    print(f"Items with ≥2 images: {sum(1 for r in by_item.values() if len(r) >= 2)}")
    labeled = build_labeled_scores(by_item, args.seed)
    print(f"Labeled pairs: {len(labeled)} "
          f"(pos={sum(1 for r in labeled if r['label']==1)}, "
          f"neg={sum(1 for r in labeled if r['label']==0)})")

    sweep = [metrics_at(labeled, t) for t in DEFAULT_THRESHOLDS]
    tier_rows = {name: metrics_at(labeled, thr) for name, thr in TIER_CUTOFFS.items()}

    print("\nthreshold  precision  recall     fpr      f1")
    for row in sweep:
        print(f"{row['threshold']:9.2f}  {row['precision']:9.4f}  "
              f"{row['recall']:6.4f}  {row['fpr']:6.4f}  {row['f1']:6.4f}")

    print("\nChosen tiers:")
    for name, row in tier_rows.items():
        print(f"  {name:8s} ≥{row['threshold']:.2f}  "
              f"P={row['precision']:.4f} R={row['recall']:.4f} FPR={row['fpr']:.4f}")

    payload = {
        "manifest": str(args.manifest),
        "split": args.split,
        "seed": args.seed,
        "tier_cutoffs": TIER_CUTOFFS,
        "tier_metrics": tier_rows,
        "sweep": sweep,
        "rationale": {
            "weak_0.55": "Minimum inclusion floor — favor recall for shortlist Weak band.",
            "possible_0.70": "Balanced operating point for typical Possible shortlists.",
            "strong_0.85": "High-precision Strong band for confident candidates.",
        },
        "pair_scores": [
            {"label": r["label"], "score": round(r["score"], 4), "kind": r["kind"]}
            for r in labeled
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
