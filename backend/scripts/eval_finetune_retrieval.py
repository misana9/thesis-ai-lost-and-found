#!/usr/bin/env python3
"""Evaluate pretrained vs fine-tuned CLIP retrieval on the held-out test split.

Usage (from backend/):
  python scripts/eval_finetune_retrieval.py
  python scripts/eval_finetune_retrieval.py --checkpoint ../dataset/checkpoints/clip_ft_best.pt
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


def load_manifest(path: Path, split: str) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return [row for row in csv.DictReader(f) if row["split"] == split]


@torch.no_grad()
def encode_paths(model, preprocess, paths: list[str], device: str, batch_size: int = 32) -> torch.Tensor:
    out = []
    for i in range(0, len(paths), batch_size):
        tensors = [preprocess(Image.open(p).convert("RGB")) for p in paths[i : i + batch_size]]
        x = torch.stack(tensors).to(device)
        e = model.encode_image(x)
        e = e / e.norm(dim=-1, keepdim=True)
        out.append(e.cpu())
    return torch.cat(out, dim=0)


@torch.no_grad()
def metrics_for(model, preprocess, rows: list[dict], device: str) -> dict:
    by_item: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        by_item[row["item_id"]].append(row["path"])

    all_paths: list[str] = []
    path_item: list[str] = []
    for item_id, paths in by_item.items():
        for p in paths:
            all_paths.append(p)
            path_item.append(item_id)
    if not all_paths:
        return {"n_queries": 0, "recall@1": 0.0, "recall@3": 0.0, "mrr": 0.0}

    gallery = encode_paths(model, preprocess, all_paths, device)
    query_items = [i for i, ps in by_item.items() if len(ps) >= 2]
    hits1 = hits3 = 0
    mrr = 0.0
    n_q = 0
    for item_id in query_items:
        paths = by_item[item_id]
        q_path = paths[0]
        q = encode_paths(model, preprocess, [q_path], device)[0]
        scores = (gallery @ q).tolist()
        ranked = [i for i in sorted(range(len(scores)), key=lambda i: scores[i], reverse=True) if all_paths[i] != q_path]
        relevant = {i for i, iid in enumerate(path_item) if iid == item_id and all_paths[i] != q_path}
        if not relevant:
            continue
        n_q += 1
        if any(i in relevant for i in ranked[:1]):
            hits1 += 1
        if any(i in relevant for i in ranked[:3]):
            hits3 += 1
        for rank, idx in enumerate(ranked, start=1):
            if idx in relevant:
                mrr += 1.0 / rank
                break
    return {
        "n_items": len(by_item),
        "n_images": len(all_paths),
        "n_queries": n_q,
        "recall@1": hits1 / n_q if n_q else 0.0,
        "recall@3": hits3 / n_q if n_q else 0.0,
        "mrr": mrr / n_q if n_q else 0.0,
    }


def load_model(device: str, checkpoint: Path | None):
    model, preprocess = clip.load("ViT-B/32", device=device)
    if checkpoint is not None:
        ckpt = torch.load(checkpoint, map_location=device, weights_only=False)
        state = ckpt["state_dict"] if isinstance(ckpt, dict) and "state_dict" in ckpt else ckpt
        model.load_state_dict(state)
        print(f"Loaded checkpoint: {checkpoint}")
    model.eval()
    return model, preprocess


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "dataset" / "manifest.csv",
    )
    parser.add_argument("--checkpoint", type=Path, default=None)
    parser.add_argument("--split", type=str, default="test")
    parser.add_argument("--device", type=str, default=None)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "dataset" / "eval_results.json",
    )
    args = parser.parse_args()

    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    rows = load_manifest(args.manifest, args.split)
    if not rows:
        raise SystemExit(f"No rows for split={args.split} in {args.manifest}")

    print(f"Evaluating split={args.split} on {device} ({len(rows)} images)")

    base_model, preprocess = load_model(device, None)
    baseline = metrics_for(base_model, preprocess, rows, device)
    print("pretrained:", json.dumps(baseline, indent=2))

    result = {"split": args.split, "pretrained": baseline, "finetuned": None}
    if args.checkpoint and args.checkpoint.exists():
        ft_model, preprocess = load_model(device, args.checkpoint)
        finetuned = metrics_for(ft_model, preprocess, rows, device)
        print("finetuned:", json.dumps(finetuned, indent=2))
        result["finetuned"] = finetuned
        result["checkpoint"] = str(args.checkpoint)
    elif args.checkpoint:
        print(f"Checkpoint not found: {args.checkpoint}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
