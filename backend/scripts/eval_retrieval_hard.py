#!/usr/bin/env python3
"""Harder campus-object retrieval baseline / comparison.

Protocol:
  - Queries come from a held-out split (default: test)
  - Gallery = ALL images in the manifest except the query image
  - Success = retrieve another photo of the same item_id

This is stricter than split-only galleries (which can score ~100% too easily).

Usage (from backend/):
  python scripts/eval_retrieval_hard.py
  python scripts/eval_retrieval_hard.py --checkpoint ../dataset/checkpoints/clip_ft_best.pt
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


def load_manifest(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@torch.no_grad()
def encode_paths(model, preprocess, paths: list[str], device: str, batch_size: int = 32) -> torch.Tensor:
    out = []
    for i in range(0, len(paths), batch_size):
        tensors = [preprocess(Image.open(p).convert("RGB")) for p in paths[i : i + batch_size]]
        x = torch.stack(tensors).to(device)
        e = model.encode_image(x)
        e = e / e.norm(dim=-1, keepdim=True)
        out.append(e.float().cpu())
    return torch.cat(out, dim=0)


def load_model(device: str, checkpoint: Path | None):
    model, preprocess = clip.load("ViT-B/32", device=device)
    if checkpoint is not None:
        ckpt = torch.load(checkpoint, map_location=device, weights_only=False)
        state = ckpt["state_dict"] if isinstance(ckpt, dict) and "state_dict" in ckpt else ckpt
        model.load_state_dict(state)
    model.eval()
    return model, preprocess


@torch.no_grad()
def evaluate(model, preprocess, rows: list[dict], query_split: str, device: str) -> dict:
    all_paths = [r["path"] for r in rows]
    all_items = [r["item_id"] for r in rows]
    all_splits = [r["split"] for r in rows]

    gallery = encode_paths(model, preprocess, all_paths, device)

    # One query per test/val item: first image in that split for the item
    by_item_query: dict[str, int] = {}
    for i, (item, split) in enumerate(zip(all_items, all_splits)):
        if split != query_split:
            continue
        if item not in by_item_query:
            by_item_query[item] = i

    hits1 = hits3 = hits5 = 0
    mrr = 0.0
    n_q = 0
    details = []

    for item_id, q_idx in sorted(by_item_query.items()):
        # Need at least one other image of same item in gallery
        relevant = [i for i, iid in enumerate(all_items) if iid == item_id and i != q_idx]
        if not relevant:
            continue

        q = gallery[q_idx]
        scores = (gallery @ q).tolist()
        ranked = [i for i in sorted(range(len(scores)), key=lambda j: scores[j], reverse=True) if i != q_idx]

        n_q += 1
        rel_set = set(relevant)
        if any(i in rel_set for i in ranked[:1]):
            hits1 += 1
        if any(i in rel_set for i in ranked[:3]):
            hits3 += 1
        if any(i in rel_set for i in ranked[:5]):
            hits5 += 1
        rr = 0.0
        for rank, idx in enumerate(ranked, start=1):
            if idx in rel_set:
                rr = 1.0 / rank
                break
        mrr += rr
        details.append(
            {
                "item_id": item_id,
                "query": all_paths[q_idx],
                "rank_first_hit": int(1 / rr) if rr else None,
                "top3_item_ids": [all_items[i] for i in ranked[:3]],
            }
        )

    return {
        "protocol": "query_split_against_full_gallery",
        "query_split": query_split,
        "gallery_images": len(all_paths),
        "gallery_items": len(set(all_items)),
        "n_queries": n_q,
        "recall@1": hits1 / n_q if n_q else 0.0,
        "recall@3": hits3 / n_q if n_q else 0.0,
        "recall@5": hits5 / n_q if n_q else 0.0,
        "mrr": mrr / n_q if n_q else 0.0,
        "per_query": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "dataset" / "manifest.csv",
    )
    parser.add_argument("--checkpoint", type=Path, default=None)
    parser.add_argument("--query-split", type=str, default="test")
    parser.add_argument("--device", type=str, default=None)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "dataset" / "baseline_hard_test.json",
    )
    args = parser.parse_args()

    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    rows = load_manifest(args.manifest)
    print(f"Hard eval on {device}: query_split={args.query_split}, gallery={len(rows)} images")

    result = {
        "manifest": str(args.manifest),
        "pretrained": None,
        "finetuned": None,
    }

    base_model, preprocess = load_model(device, None)
    baseline = evaluate(base_model, preprocess, rows, args.query_split, device)
    result["pretrained"] = {k: v for k, v in baseline.items() if k != "per_query"}
    result["pretrained_per_query"] = baseline["per_query"]
    print("pretrained:", json.dumps(result["pretrained"], indent=2))

    if args.checkpoint and args.checkpoint.exists():
        ft_model, preprocess = load_model(device, args.checkpoint)
        finetuned = evaluate(ft_model, preprocess, rows, args.query_split, device)
        result["finetuned"] = {k: v for k, v in finetuned.items() if k != "per_query"}
        result["finetuned_per_query"] = finetuned["per_query"]
        result["checkpoint"] = str(args.checkpoint)
        print("finetuned:", json.dumps(result["finetuned"], indent=2))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
