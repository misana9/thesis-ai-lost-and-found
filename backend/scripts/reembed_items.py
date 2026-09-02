#!/usr/bin/env python3
"""Regenerate CLIP embeddings for all lost/found rows after fine-tuning.

Usage (from backend/, with DB env / Docker network available):
  python scripts/reembed_items.py
  python scripts/reembed_items.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from clip_service import encode_pil_image, encode_text  # noqa: E402
from database import SessionLocal  # noqa: E402
import models  # noqa: E402

UPLOAD_DIR = ROOT / "uploads"


def reembed(*, dry_run: bool = False) -> dict:
    db = SessionLocal()
    lost_updated = found_updated = lost_skipped = found_skipped = 0
    try:
        for item in db.query(models.LostItem).all():
            changed = False
            if item.image_path:
                path = UPLOAD_DIR / item.image_path
                if path.is_file():
                    try:
                        emb = encode_pil_image(Image.open(path))
                        if not dry_run:
                            item.image_embedding = emb
                        changed = True
                    except Exception:
                        lost_skipped += 1
                else:
                    lost_skipped += 1
            if item.description:
                try:
                    emb = encode_text(item.description)
                    if not dry_run:
                        item.text_embedding = emb
                    changed = True
                except Exception:
                    lost_skipped += 1
            if changed:
                lost_updated += 1

        for item in db.query(models.FoundItem).all():
            changed = False
            if item.image_path:
                path = UPLOAD_DIR / item.image_path
                if path.is_file():
                    try:
                        emb = encode_pil_image(Image.open(path))
                        if not dry_run:
                            item.image_embedding = emb
                        changed = True
                    except Exception:
                        found_skipped += 1
                else:
                    found_skipped += 1
            if item.description:
                try:
                    emb = encode_text(item.description)
                    if not dry_run:
                        item.text_embedding = emb
                    changed = True
                except Exception:
                    found_skipped += 1
            if changed:
                found_updated += 1

        if not dry_run:
            db.commit()
    finally:
        db.close()

    return {
        "dry_run": dry_run,
        "lost_updated": lost_updated,
        "found_updated": found_updated,
        "lost_skipped": lost_skipped,
        "found_skipped": found_skipped,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = reembed(dry_run=args.dry_run)
    print(result)


if __name__ == "__main__":
    main()
