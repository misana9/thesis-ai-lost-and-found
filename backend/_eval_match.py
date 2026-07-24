"""Offline matching-quality experiment (no DB).

Encodes Objects/<type>-/<N>_<type>/ folders directly with CLIP and evaluates how
often the SAME physical item (same folder) ranks #1 under different weight schemes.
"""
import os, re
from PIL import Image
from clip_service import encode_pil_image, encode_text, cosine_similarity

OBJ = "/tmp/Objects"
CATMAP = {
    "calculator": "School Supplies", "earphone": "Gadget Accessories", "ipad": "Gadgets",
    "minifan": "Electronics", "phone": "Gadgets", "powerbank": "Gadget Accessories",
    "key": "Other", "tumbler": "Water Bottle", "wallet": "Wallet / Purse",
    "id": "Other", "pen": "Other",
}


def natkey(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def imgs_in(folder):
    fs = [f for f in os.listdir(folder)
          if f.lower().endswith((".jpg", ".jpeg", ".png")) and not f.startswith(".")]
    return sorted(fs, key=natkey)


def cat_mult(raw, same):
    return min((raw * 1.10 if same else raw * 0.75), 0.99)


# fn(ii, ti, cr, tt): image-to-image, text_to_image, cross(found_text->lost_img), text-to-text
SCHEMES = {
    "A old (img.60/txt2img.25/cross.15)": lambda ii, ti, cr, tt: ii*0.60 + ti*0.25 + cr*0.15,
    "F img.72/t2t.28 (current)":          lambda ii, ti, cr, tt: ii*0.72 + tt*0.28,
    "I img.82/t2t.18":                    lambda ii, ti, cr, tt: ii*0.82 + tt*0.18,
    "J img.88/t2t.12":                    lambda ii, ti, cr, tt: ii*0.88 + tt*0.12,
    "E image-only (1.0)":                 lambda ii, ti, cr, tt: ii,
}
# Precision note: same-category DIFFERENT items are counted as clutter when they
# cross the display threshold. We report mean matches shown per query.


def main():
    items = []
    for tdir in sorted(os.listdir(OBJ)):
        tp = os.path.join(OBJ, tdir)
        if not os.path.isdir(tp):
            continue
        tname = tdir.rstrip("-").strip()
        if tname not in CATMAP:
            continue
        for inst in sorted(os.listdir(tp), key=natkey):
            ip = os.path.join(tp, inst)
            if not os.path.isdir(ip):
                continue
            ims = imgs_in(ip)
            if len(ims) >= 2:
                items.append((tname, inst, ip, ims))

    print(f"Encoding {len(items)} item instances...")
    cands, queries = [], []
    for (tname, inst, ip, ims) in items:
        label = f"{tname}/{inst}"
        cat = CATMAP[tname]
        found_img = encode_pil_image(Image.open(os.path.join(ip, ims[0])).convert("RGB"))
        qfn = ims[len(ims)//2] if ims[len(ims)//2] != ims[0] else ims[1]
        lost_img = encode_pil_image(Image.open(os.path.join(ip, qfn)).convert("RGB"))
        text_emb = encode_text(tname)  # generic per-type description
        cands.append({"label": label, "cat": cat, "img": found_img, "text": text_emb})
        queries.append({"label": label, "cat": cat, "img": lost_img, "text": text_emb})

    # Precompute pairwise cosines
    print("Scoring...\n")
    THRESH = [0.55, 0.65, 0.72]
    results = {name: {"rank1": 0, "top3": 0, "top5": 0, "mrr": 0.0,
                      "shown": {t: 0 for t in THRESH}} for name in SCHEMES}
    for q in queries:
        rows = []
        for c in cands:
            ii = cosine_similarity(q["img"], c["img"])
            ti = cosine_similarity(q["text"], c["img"])
            cr = cosine_similarity(c["text"], q["img"])
            tt = cosine_similarity(q["text"], c["text"])
            same = q["cat"] == c["cat"]
            rows.append((c["label"], ii, ti, cr, tt, same))
        for name, fn in SCHEMES.items():
            scored = sorted(
                ((lbl, cat_mult(fn(ii, ti, cr, tt), same)) for (lbl, ii, ti, cr, tt, same) in rows),
                key=lambda x: x[1], reverse=True,
            )
            rank = next(i for i, (lbl, _) in enumerate(scored, 1) if lbl == q["label"])
            if rank == 1:
                results[name]["rank1"] += 1
            if rank <= 3:
                results[name]["top3"] += 1
            if rank <= 5:
                results[name]["top5"] += 1
            results[name]["mrr"] += 1.0 / rank
            for t in THRESH:
                results[name]["shown"][t] += sum(1 for _, sc in scored if sc >= t)

    n = len(queries)
    print("=" * 92)
    print(f"{'SCHEME':<34}{'rank1':>8}{'top3':>8}{'top5':>8}{'MRR':>7}"
          f"{'shown@.55':>11}{'shown@.65':>11}{'shown@.72':>11}")
    print("(shown = avg # matches displayed per query; lower = less clutter)")
    print("=" * 92)
    for name in SCHEMES:
        r = results[name]
        s = r["shown"]
        print(f"{name:<34}{r['rank1']:>3}/{n:<4}{r['top3']:>3}/{n:<4}{r['top5']:>3}/{n:<4}"
              f"{r['mrr']/n:>7.3f}{s[0.55]/n:>11.1f}{s[0.65]/n:>11.1f}{s[0.72]/n:>11.1f}")
    print("=" * 92)


if __name__ == "__main__":
    main()
