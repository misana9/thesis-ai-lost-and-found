#!/usr/bin/env python3
"""Light contrastive fine-tune of CLIP ViT-B/32 on campus item photos.

Freezes most of CLIP; trains the image projection + last transformer block
with InfoNCE on same-item vs different-item image pairs.

Usage (from backend/, with venv active):
  python scripts/build_finetune_manifest.py
  python scripts/finetune_clip.py --epochs 8
  python scripts/eval_finetune_retrieval.py --checkpoint ../dataset/checkpoints/clip_ft_best.pt
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import clip
import torch
import torch.nn.functional as F
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_manifest(path: Path, split: str | None = None) -> list[dict]:
    rows = []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if split is None or row["split"] == split:
                rows.append(row)
    return rows


class ItemPairDataset(Dataset):
    def __init__(self, rows: list[dict], preprocess, train: bool):
        self.preprocess = preprocess
        self.train = train
        by_item: dict[str, list[str]] = defaultdict(list)
        for row in rows:
            by_item[row["item_id"]].append(row["path"])
        # Need at least 2 images for a positive pair
        self.by_item = {k: v for k, v in by_item.items() if len(v) >= 2}
        self.item_ids = sorted(self.by_item.keys())
        if len(self.item_ids) < 2:
            raise ValueError("Need at least 2 item_ids with >=2 images each for contrastive training")

        self.aug = transforms.Compose(
            [
                transforms.RandomResizedCrop(224, scale=(0.7, 1.0)),
                transforms.RandomHorizontalFlip(),
                transforms.ColorJitter(0.2, 0.2, 0.2, 0.05),
                transforms.RandomRotation(12),
            ]
        )

    def __len__(self) -> int:
        return max(len(self.item_ids) * 4, 64)

    def _load(self, path: str) -> torch.Tensor:
        img = Image.open(path).convert("RGB")
        if self.train:
            img = self.aug(img)
        return self.preprocess(img)

    def __getitem__(self, idx: int):
        anchor_id = self.item_ids[idx % len(self.item_ids)]
        paths = self.by_item[anchor_id]
        a, p = random.sample(paths, 2) if len(paths) >= 2 else (paths[0], paths[0])
        # hard-ish negative: different item, prefer same category stem if possible
        neg_id = random.choice([i for i in self.item_ids if i != anchor_id])
        n = random.choice(self.by_item[neg_id])
        return {
            "anchor": self._load(a),
            "positive": self._load(p),
            "negative": self._load(n),
            "item_id": anchor_id,
        }


def collate(batch):
    return {
        "anchor": torch.stack([b["anchor"] for b in batch]),
        "positive": torch.stack([b["positive"] for b in batch]),
        "negative": torch.stack([b["negative"] for b in batch]),
        "item_id": [b["item_id"] for b in batch],
    }


def set_trainable(model) -> list[torch.nn.Parameter]:
    """Freeze everything except image proj + last resblock."""
    for p in model.parameters():
        p.requires_grad = False

    trainable: list[torch.nn.Parameter] = []
    # Visual projection
    if hasattr(model.visual, "proj") and model.visual.proj is not None:
        if isinstance(model.visual.proj, torch.nn.Parameter):
            model.visual.proj.requires_grad = True
            trainable.append(model.visual.proj)
    # Last transformer block
    if hasattr(model.visual, "transformer"):
        last = model.visual.transformer.resblocks[-1]
        for p in last.parameters():
            p.requires_grad = True
            trainable.append(p)
    if hasattr(model.visual, "ln_post"):
        for p in model.visual.ln_post.parameters():
            p.requires_grad = True
            trainable.append(p)
    if not trainable:
        # Fallback: train full visual tower lightly
        for p in model.visual.parameters():
            p.requires_grad = True
            trainable.append(p)
    return trainable


def info_nce(anchor: torch.Tensor, positive: torch.Tensor, temperature: float = 0.07) -> torch.Tensor:
    """Batch InfoNCE: each anchor matched to its positive; other positives are negatives."""
    a = F.normalize(anchor, dim=-1)
    p = F.normalize(positive, dim=-1)
    logits = a @ p.T / temperature
    labels = torch.arange(a.shape[0], device=a.device)
    return F.cross_entropy(logits, labels)


@torch.no_grad()
def encode_images(model, preprocess, paths: list[str], device: str, batch_size: int = 32) -> torch.Tensor:
    embs = []
    for i in range(0, len(paths), batch_size):
        chunk = paths[i : i + batch_size]
        tensors = []
        for path in chunk:
            img = preprocess(Image.open(path).convert("RGB"))
            tensors.append(img)
        x = torch.stack(tensors).to(device=device, dtype=torch.float32)
        e = model.encode_image(x).float()
        e = e / e.norm(dim=-1, keepdim=True)
        embs.append(e.cpu())
    return torch.cat(embs, dim=0)


@torch.no_grad()
def retrieval_metrics(model, preprocess, rows: list[dict], device: str) -> dict:
    by_item: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        by_item[row["item_id"]].append(row["path"])
    # queries: items with >=2 images; gallery = all images
    item_ids = [i for i, ps in by_item.items() if len(ps) >= 2]
    if not item_ids:
        return {"n_queries": 0, "recall@1": 0.0, "recall@3": 0.0, "mrr": 0.0}

    all_paths: list[str] = []
    path_item: list[str] = []
    for item_id, paths in by_item.items():
        for p in paths:
            all_paths.append(p)
            path_item.append(item_id)
    gallery = encode_images(model, preprocess, all_paths, device)

    hits1 = hits3 = 0
    mrr = 0.0
    n_q = 0
    for item_id in item_ids:
        paths = by_item[item_id]
        # use first image as query, remaining same-item as relevant
        q_path = paths[0]
        q = encode_images(model, preprocess, [q_path], device)[0]
        scores = (gallery @ q).tolist()
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        # remove exact query path from ranking
        ranked = [i for i in ranked if all_paths[i] != q_path]
        relevant = {i for i, iid in enumerate(path_item) if iid == item_id and all_paths[i] != q_path}
        if not relevant:
            continue
        n_q += 1
        top = ranked[:3]
        if any(i in relevant for i in ranked[:1]):
            hits1 += 1
        if any(i in relevant for i in top):
            hits3 += 1
        for rank, idx in enumerate(ranked, start=1):
            if idx in relevant:
                mrr += 1.0 / rank
                break
    return {
        "n_queries": n_q,
        "recall@1": hits1 / n_q if n_q else 0.0,
        "recall@3": hits3 / n_q if n_q else 0.0,
        "mrr": mrr / n_q if n_q else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "dataset" / "manifest.csv",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "dataset" / "checkpoints",
    )
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--temperature", type=float, default=0.07)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", type=str, default=None)
    args = parser.parse_args()

    random.seed(args.seed)
    torch.manual_seed(args.seed)

    if args.device:
        device = args.device
    elif torch.cuda.is_available():
        device = "cuda"
    elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        device = "mps"
    else:
        device = "cpu"
    print(f"Device: {device}")

    model, preprocess = clip.load("ViT-B/32", device=device)
    # MPS + CLIP half precision often explodes to NaN; keep float32 for training.
    model = model.float()
    trainable = set_trainable(model)
    print(f"Trainable tensors: {len(trainable)}")

    train_rows = load_manifest(args.manifest, "train")
    val_rows = load_manifest(args.manifest, "val")
    if not val_rows:
        val_rows = load_manifest(args.manifest, "test")

    train_ds = ItemPairDataset(train_rows, preprocess, train=True)
    loader = DataLoader(
        train_ds,
        batch_size=min(args.batch_size, max(2, len(train_ds.item_ids))),
        shuffle=True,
        num_workers=0,
        collate_fn=collate,
        drop_last=True,
    )

    optim = torch.optim.AdamW(trainable, lr=args.lr, weight_decay=0.01)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    baseline = retrieval_metrics(model, preprocess, val_rows, device)
    print("Baseline val:", json.dumps(baseline, indent=2))
    (args.out_dir / "baseline_val.json").write_text(json.dumps(baseline, indent=2))

    best_mrr = baseline.get("mrr", 0.0)
    best_loss = float("inf")
    best_path = args.out_dir / "clip_ft_best.pt"
    history = []

    saved_best = False
    model.train()
    for epoch in range(1, args.epochs + 1):
        total = 0.0
        steps = 0
        skipped = 0
        for batch in loader:
            anchor = batch["anchor"].to(device, dtype=torch.float32)
            positive = batch["positive"].to(device, dtype=torch.float32)
            # Also mix explicit negatives into the positive bank by concatenating
            negative = batch["negative"].to(device, dtype=torch.float32)
            # Encode
            a = model.encode_image(anchor).float()
            p = model.encode_image(positive).float()
            n = model.encode_image(negative).float()
            # Build bank: positives in diagonal slots; append negatives for harder push
            bank = torch.cat([p, n], dim=0)
            a_n = F.normalize(a, dim=-1)
            bank_n = F.normalize(bank, dim=-1)
            logits = a_n @ bank_n.T / args.temperature
            labels = torch.arange(a.shape[0], device=device)
            loss = F.cross_entropy(logits, labels)

            if not torch.isfinite(loss):
                skipped += 1
                optim.zero_grad(set_to_none=True)
                continue

            optim.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(trainable, 1.0)
            optim.step()
            total += float(loss.item())
            steps += 1

        model.eval()
        metrics = retrieval_metrics(model, preprocess, val_rows, device)
        model.train()
        avg = total / max(steps, 1)
        row = {"epoch": epoch, "loss": avg, "skipped": skipped, **metrics}
        history.append(row)
        print(json.dumps(row))

        # Prefer higher val MRR; on ties (common when val is saturated), keep lowest train loss.
        improved = steps > 0 and (
            metrics["mrr"] > best_mrr + 1e-12
            or (abs(metrics["mrr"] - best_mrr) <= 1e-12 and avg < best_loss)
        )
        if improved:
            best_mrr = metrics["mrr"]
            best_loss = avg
            torch.save(
                {
                    "model": "ViT-B/32",
                    "state_dict": model.state_dict(),
                    "epoch": epoch,
                    "train_loss": avg,
                    "val": metrics,
                    "baseline_val": baseline,
                },
                best_path,
            )
            saved_best = True
            print(f"Saved best -> {best_path} (epoch={epoch}, loss={avg:.4f}, mrr={metrics['mrr']:.4f})")

    last_path = args.out_dir / "clip_ft_last.pt"
    if any(r.get("loss") == r.get("loss") for r in history):  # finite-loss epochs exist
        torch.save(
            {
                "model": "ViT-B/32",
                "state_dict": model.state_dict(),
                "epoch": args.epochs,
                "history": history,
                "baseline_val": baseline,
            },
            last_path,
        )
    (args.out_dir / "train_history.json").write_text(json.dumps(history, indent=2))
    if not saved_best:
        print(
            "No checkpoint beat baseline val MRR; keeping pretrained baseline. "
            f"Best tracked MRR={best_mrr:.4f}."
        )
    else:
        print(
            f"Done. Best epoch checkpoint: MRR={best_mrr:.4f}, loss={best_loss:.4f}. "
            f"Path: {best_path}"
        )


if __name__ == "__main__":
    main()
