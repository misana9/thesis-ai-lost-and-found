#!/usr/bin/env python3
"""Generate multiple baseline retrieval tests for thesis comparison.

Tests:
  A) image->image same-item (full gallery)  [often near-saturated]
  B) image->image within same category only (harder distractors)
  C) text->image using 'a photo of a {category_stem}'

Usage (from backend/):
  python scripts/generate_baseline_suite.py
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import clip
import torch
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@torch.no_grad()
def encode_images(model, preprocess, paths: list[str], device: str, bs: int = 32) -> torch.Tensor:
    out = []
    for i in range(0, len(paths), bs):
        batch = torch.stack([preprocess(Image.open(p).convert("RGB")) for p in paths[i : i + bs]]).to(device)
        e = model.encode_image(batch)
        e = e / e.norm(dim=-1, keepdim=True)
        out.append(e.float().cpu())
    return torch.cat(out, dim=0)


@torch.no_grad()
def encode_texts(model, texts: list[str], device: str, bs: int = 64) -> torch.Tensor:
    out = []
    for i in range(0, len(texts), bs):
        tokens = clip.tokenize(texts[i : i + bs], truncate=True).to(device)
        e = model.encode_text(tokens)
        e = e / e.norm(dim=-1, keepdim=True)
        out.append(e.float().cpu())
    return torch.cat(out, dim=0)


def summarize(ranks_hit: list[int | None]) -> dict:
    usable = [r for r in ranks_hit if r is not None]
    n = len(usable)
    if not n:
        return {"n_queries": 0, "recall@1": 0.0, "recall@3": 0.0, "recall@5": 0.0, "mrr": 0.0}
    return {
        "n_queries": n,
        "recall@1": sum(1 for r in usable if r <= 1) / n,
        "recall@3": sum(1 for r in usable if r <= 3) / n,
        "recall@5": sum(1 for r in usable if r <= 5) / n,
        "mrr": sum(1.0 / r for r in usable) / n,
    }


@torch.no_grad()
def test_image_image(model, preprocess, rows: list[dict], query_split: str, device: str, same_category_only: bool) -> dict:
    paths = [r["path"] for r in rows]
    items = [r["item_id"] for r in rows]
    stems = [r["category_stem"] for r in rows]
    splits = [r["split"] for r in rows]
    emb = encode_images(model, preprocess, paths, device)

    # first image of each query-split item as query (query_split="all" = every item)
    qmap: dict[str, int] = {}
    for i, (item, split) in enumerate(zip(items, splits)):
        if query_split != "all" and split != query_split:
            continue
        if item not in qmap:
            qmap[item] = i

    ranks: list[int | None] = []
    for item, q in sorted(qmap.items()):
        stem = stems[q]
        cand = []
        for i in range(len(paths)):
            if i == q:
                continue
            if same_category_only and stems[i] != stem:
                continue
            cand.append(i)
        relevant = [i for i in cand if items[i] == item]
        if not relevant:
            ranks.append(None)
            continue
        qv = emb[q]
        scores = [(float(emb[i] @ qv), i) for i in cand]
        scores.sort(reverse=True)
        ranked_ids = [i for _, i in scores]
        rank = next((r for r, i in enumerate(ranked_ids, 1) if i in relevant), None)
        ranks.append(rank)

    label = "image_to_image_same_category" if same_category_only else "image_to_image_full_gallery"
    return {"test": label, "query_split": query_split, **summarize(ranks)}


def test_text_image_full(model, preprocess, rows: list[dict], query_split: str, device: str) -> dict:
    by_item = defaultdict(list)
    stem_of = {}
    item_splits = defaultdict(set)
    for r in rows:
        by_item[r["item_id"]].append(r["path"])
        stem_of[r["item_id"]] = r["category_stem"]
        item_splits[r["item_id"]].add(r["split"])

    all_paths, path_item = [], []
    for item, ps in by_item.items():
        for p in ps:
            all_paths.append(p)
            path_item.append(item)
    img_emb = encode_images(model, preprocess, all_paths, device)

    if query_split == "all":
        query_items = sorted(by_item.keys())
    else:
        query_items = sorted(i for i, sp in item_splits.items() if query_split in sp)
    texts = [f"a photo of a {stem_of[i].replace('_', ' ')}" for i in query_items]
    txt_emb = encode_texts(model, texts, device)

    ranks: list[int | None] = []
    for qi, item in enumerate(query_items):
        relevant = {idx for idx, iid in enumerate(path_item) if iid == item}
        if not relevant:
            ranks.append(None)
            continue
        scores = (img_emb @ txt_emb[qi]).tolist()
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        rank = next((r for r, i in enumerate(ranked, 1) if i in relevant), None)
        ranks.append(rank)

    return {"test": "text_to_image_stem_prompt", "query_split": query_split, **summarize(ranks)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path(__file__).resolve().parents[2] / "dataset" / "manifest.csv")
    parser.add_argument("--checkpoint", type=Path, default=None)
    parser.add_argument("--query-split", type=str, default="test")
    parser.add_argument("--device", type=str, default=None)
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[2] / "dataset" / "baseline_suite.json")
    args = parser.parse_args()

    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    rows = load_rows(args.manifest)
    model, preprocess = clip.load("ViT-B/32", device=device)
    tag = "pretrained"
    if args.checkpoint and args.checkpoint.exists():
        ckpt = torch.load(args.checkpoint, map_location=device, weights_only=False)
        state = ckpt["state_dict"] if isinstance(ckpt, dict) and "state_dict" in ckpt else ckpt
        model.load_state_dict(state)
        tag = "finetuned"
    model.eval()

    suite = {
        "model": tag,
        "checkpoint": str(args.checkpoint) if args.checkpoint else None,
        "query_split": args.query_split,
        "n_images": len(rows),
        "tests": [
            test_image_image(model, preprocess, rows, args.query_split, device, same_category_only=False),
            test_image_image(model, preprocess, rows, args.query_split, device, same_category_only=True),
            test_text_image_full(model, preprocess, rows, args.query_split, device),
        ],
    }
    print(json.dumps(suite, indent=2))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(suite, indent=2), encoding="utf-8")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
