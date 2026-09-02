#!/usr/bin/env python3
"""Keyword baseline vs multimodal CLIP matching on the curated Objects set.

Traditional keyword matching: token overlap / SequenceMatcher on category-stem
phrases (no embeddings). Multimodal: compute_match fusion scores.

Reports Precision@1, Recall@1 / Hit@1, MRR, and inclusion rates at the
AMAlost tier floors. This is a *local* control on your dataset — not AUFound
published metrics.

Usage (from backend/):
  python scripts/eval_keyword_baseline.py
  python scripts/eval_keyword_baseline.py --split test --out ../dataset/keyword_vs_multimodal.json
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from clip_service import cosine_similarity, encode_image, encode_text  # noqa: E402
from matching import compute_match  # noqa: E402

STOP = {"a", "an", "the", "of", "photo", "found", "lost", "item", "my"}


def tokenize(text: str) -> set[str]:
    toks = re.findall(r"[a-z0-9]+", text.lower())
    return {t for t in toks if t not in STOP and len(t) > 1}


def keyword_score(query: str, candidate: str) -> float:
    q, c = tokenize(query), tokenize(candidate)
    if not q or not c:
        return SequenceMatcher(None, query.lower(), candidate.lower()).ratio() * 0.5
    jaccard = len(q & c) / len(q | c)
    seq = SequenceMatcher(None, query.lower(), candidate.lower()).ratio()
    return 0.7 * jaccard + 0.3 * seq


def load_rows(manifest: Path, split: str | None) -> list[dict]:
    rows = []
    with manifest.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if split and row["split"] != split:
                continue
            rows.append(row)
    return rows


def multimodal_score(lost_img: str, found_img: str, lost_text: str, found_text: str,
                     lost_cat: str, found_cat: str) -> float:
    final, _, _, _ = compute_match(
        text_to_image=cosine_similarity(encode_text(lost_text), encode_image(found_img)),
        image_to_image=cosine_similarity(encode_image(lost_img), encode_image(found_img)),
        found_text_to_lost_image=cosine_similarity(encode_text(found_text), encode_image(lost_img)),
        lost_category=lost_cat,
        found_category=found_cat,
    )
    return float(final)


def rank_metrics(ranks: list[int | None]) -> dict:
    n = len(ranks)
    if not n:
        return {"n_queries": 0, "hit@1": 0.0, "recall@1": 0.0, "mrr": 0.0}
    hits1 = sum(1 for r in ranks if r == 1)
    mrr = sum((1.0 / r) for r in ranks if r is not None) / n
    return {
        "n_queries": n,
        "hit@1": round(hits1 / n, 4),
        "recall@1": round(hits1 / n, 4),
        "mrr": round(mrr, 4),
    }


def inclusion_at(scores_labels: list[tuple[float, int]], threshold: float) -> dict:
    # Binary: does the true match score ≥ threshold? (per-query true pair only)
    # Plus FPR on hard negatives collected alongside.
    pos = [s for s, y in scores_labels if y == 1]
    neg = [s for s, y in scores_labels if y == 0]
    tp = sum(1 for s in pos if s >= threshold)
    fn = len(pos) - tp
    fp = sum(1 for s in neg if s >= threshold)
    tn = len(neg) - fp
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    return {
        "threshold": threshold,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "fpr": round(fpr, 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "dataset" / "manifest.csv",
    )
    parser.add_argument("--split", type=str, default="test")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--gallery-per-query", type=int, default=12)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "dataset" / "keyword_vs_multimodal.json",
    )
    args = parser.parse_args()

    rows = load_rows(args.manifest, args.split)
    by_item: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_item[r["item_id"]].append(r)

    item_ids = [i for i, rs in by_item.items() if len(rs) >= 2]
    rng = random.Random(args.seed)
    all_items = list(by_item.keys())

    kw_ranks: list[int | None] = []
    mm_ranks: list[int | None] = []
    kw_pair_scores: list[tuple[float, int]] = []
    mm_pair_scores: list[tuple[float, int]] = []

    for item_id in item_ids:
        rs = by_item[item_id]
        q_row, truth_row = rng.sample(rs, 2)
        stem = q_row["category_stem"].replace("_", " ")
        cat = q_row["system_category"]
        query_text = f"lost {stem}"
        truth_text = f"found {stem}"

        # Gallery: true match + distractors
        distractors = [i for i in all_items if i != item_id]
        rng.shuffle(distractors)
        gallery_ids = [item_id] + distractors[: max(0, args.gallery_per_query - 1)]
        gallery = []
        for gid in gallery_ids:
            cand = truth_row if gid == item_id else rng.choice(by_item[gid])
            gallery.append(cand)

        # Keyword ranking (text only)
        kw_scored = []
        for cand in gallery:
            c_stem = cand["category_stem"].replace("_", " ")
            cand_text = f"found {c_stem}"
            s = keyword_score(query_text, cand_text)
            kw_scored.append((s, cand["item_id"]))
            kw_pair_scores.append((s, 1 if cand["item_id"] == item_id else 0))
        kw_scored.sort(key=lambda x: x[0], reverse=True)
        kw_rank = next((i for i, (_, iid) in enumerate(kw_scored, 1) if iid == item_id), None)
        kw_ranks.append(kw_rank)

        # Multimodal ranking
        mm_scored = []
        for cand in gallery:
            c_stem = cand["category_stem"].replace("_", " ")
            cand_text = f"found {c_stem}"
            s = multimodal_score(
                q_row["path"], cand["path"], query_text, cand_text,
                cat, cand["system_category"],
            )
            mm_scored.append((s, cand["item_id"]))
            mm_pair_scores.append((s, 1 if cand["item_id"] == item_id else 0))
        mm_scored.sort(key=lambda x: x[0], reverse=True)
        mm_rank = next((i for i, (_, iid) in enumerate(mm_scored, 1) if iid == item_id), None)
        mm_ranks.append(mm_rank)

    kw_metrics = rank_metrics(kw_ranks)
    mm_metrics = rank_metrics(mm_ranks)
    tiers = {
        "weak_0.55": inclusion_at(mm_pair_scores, 0.55),
        "possible_0.70": inclusion_at(mm_pair_scores, 0.70),
        "strong_0.85": inclusion_at(mm_pair_scores, 0.85),
    }

    print("Keyword baseline:", kw_metrics)
    print("Multimodal CLIP:", mm_metrics)
    print("Multimodal inclusion @ tiers:", tiers)

    payload = {
        "manifest": str(args.manifest),
        "split": args.split,
        "seed": args.seed,
        "gallery_per_query": args.gallery_per_query,
        "note": (
            "Local control on curated Objects dataset. Keyword = token/SequenceMatcher "
            "overlap on stem phrases; Multimodal = AMAlost adaptive fusion. "
            "Not comparable to AUFound published scores."
        ),
        "keyword": kw_metrics,
        "multimodal": mm_metrics,
        "delta_hit@1": round(mm_metrics["hit@1"] - kw_metrics["hit@1"], 4),
        "delta_mrr": round(mm_metrics["mrr"] - kw_metrics["mrr"], 4),
        "multimodal_tier_inclusion": tiers,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
