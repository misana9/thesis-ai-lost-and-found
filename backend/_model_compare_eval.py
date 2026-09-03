# one found + one lost (diff angle) per Objects instance → rank-1 accuracy
from __future__ import annotations

import json
import os
import re
import sys
import uuid
import urllib.error
import urllib.request

API = os.environ.get("API_BASE")
OBJ = os.environ.get("OBJECTS_DIR", os.path.join(os.path.dirname(__file__), "..", "Objects"))
MODEL_TAG = os.environ.get("MODEL_TAG", "unknown")

CAT = {
    "calculator": "School Supplies",
    "pen": "School Supplies",
    "earphone": "Gadget Accessories",
    "powerbank": "Gadget Accessories",
    "ipad": "Gadgets",
    "phone": "Gadgets",
    "minifan": "Electronics",
    "key": "Other",
    "id": "Other",
    "wallet": "Wallet / Purse",
    "tumbler": "Water Bottle",
}


def req(method, path, data=None, token=None):
    headers = {}
    body = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(API + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=180) as x:
            return x.status, json.loads(x.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def multipart(fields, files):
    boundary = "----B" + uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
        )
    for k, (filename, content, ctype) in files.items():
        parts.append(
            (
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; "
                f'filename="{filename}"\r\nContent-Type: {ctype}\r\n\r\n'
            ).encode()
            + content
            + b"\r\n"
        )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def post_multipart(path, fields, files, token=None):
    body, ctype = multipart(fields, files)
    headers = {"Content-Type": ctype}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(API + path, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(r, timeout=300) as x:
            return x.status, json.loads(x.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {"detail": str(e)}


def auth(email, name):
    s, d = req("POST", "/auth/register", {"name": name, "email": email, "password": "password123"})
    token = (d.get("dev_verify_url") or "").split("token=")[-1]
    if token:
        req("GET", f"/auth/verify?token={token}")
    s, d = req("POST", "/auth/login", {"email": email, "password": "password123"})
    return d.get("access_token")


def natkey(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def list_imgs(folder):
    exts = {".jpg", ".jpeg", ".png", ".webp"}
    files = [
        f
        for f in os.listdir(folder)
        if os.path.splitext(f.lower())[1] in exts and not f.startswith(".")
    ]
    return sorted(files, key=natkey)


def content_type(fn):
    return "image/png" if fn.lower().endswith(".png") else "image/jpeg"


def discover_instances():
    rows = []
    for entry in sorted(os.listdir(OBJ)):
        type_path = os.path.join(OBJ, entry)
        if not os.path.isdir(type_path) or entry.startswith(".") or entry in ("objects2", "sports"):
            continue
        type_name = entry.rstrip("-")
        if type_name not in CAT:
            continue
        for inst in sorted(os.listdir(type_path), key=natkey):
            ip = os.path.join(type_path, inst)
            if not os.path.isdir(ip) or inst.startswith("."):
                continue
            imgs = list_imgs(ip)
            if len(imgs) < 2:
                continue
            rows.append(
                {
                    "type": type_name,
                    "instance": inst,
                    "label": f"{type_name}/{inst}",
                    "category": CAT[type_name],
                    "found_img": os.path.join(ip, imgs[0]),
                    "lost_img": os.path.join(ip, imgs[1]),
                    "found_name": imgs[0],
                    "lost_name": imgs[1],
                }
            )
    return rows


def main():
    instances = discover_instances()
    tag = uuid.uuid4().hex[:8]
    finder = auth(f"finder_{tag}@eval.edu", f"Finder {tag}")
    owner = auth(f"owner_{tag}@eval.edu", f"Owner {tag}")
    if not finder or not owner:
        print("AUTH_FAILED", file=sys.stderr)
        sys.exit(1)

    print(f"MODEL_TAG={MODEL_TAG} instances={len(instances)} tag={tag}")
    found_map = {}  # found_id -> label

    for row in instances:
        with open(row["found_img"], "rb") as f:
            data = f.read()
        s, d = post_multipart(
            "/found",
            {
                "category": row["category"],
                "description": row["type"],
                "finder_email": f"finder_{tag}@eval.edu",
                "location": "Campus",
            },
            {"image": (row["found_name"], data, content_type(row["found_name"]))},
            token=finder,
        )
        if s != 200:
            print(f"FOUND_FAIL {row['label']}: {s} {d}")
            continue
        found_map[d["id"]] = row["label"]
        row["found_id"] = d["id"]
        print(f"FOUND ok {row['label']} -> {d['id'][:8]}")

    results = []
    for row in instances:
        if "found_id" not in row:
            continue
        with open(row["lost_img"], "rb") as f:
            data = f.read()
        s, d = post_multipart(
            "/lost",
            {
                "category": row["category"],
                "description": row["type"],
                "email": f"owner_{tag}@eval.edu",
                "location": "Campus",
            },
            {"image": (row["lost_name"], data, content_type(row["lost_name"]))},
            token=owner,
        )
        if s != 200:
            print(f"LOST_FAIL {row['label']}: {s} {d}")
            continue
        matches = d.get("matches") or []
        # Prefer ranking among our uploaded pool; also show global rank-1
        our = [m for m in matches if m.get("id") in found_map]
        # API already sorts globally; rebuild rank among our set
        our_sorted = sorted(our, key=lambda m: m["score"], reverse=True)
        global_top = matches[0] if matches else None
        our_top = our_sorted[0] if our_sorted else None

        truth_rank_global = None
        for i, m in enumerate(matches, 1):
            if m.get("id") == row["found_id"]:
                truth_rank_global = i
                break
        truth_rank_ours = None
        for i, m in enumerate(our_sorted, 1):
            if m.get("id") == row["found_id"]:
                truth_rank_ours = i
                break

        g_label = found_map.get(global_top["id"], f"OTHER/{global_top.get('category')}") if global_top else None
        o_label = found_map.get(our_top["id"]) if our_top else None
        same_item = truth_rank_global == 1
        same_type_diff_inst = False
        if global_top and not same_item and g_label:
            # same type prefix, different instance
            g_type = g_label.split("/")[0] if "/" in str(g_label) else None
            same_type_diff_inst = g_type == row["type"] and g_label != row["label"]

        rec = {
            "query": row["label"],
            "truth_found": row["label"],
            "n_matches": len(matches),
            "n_our_matches": len(our_sorted),
            "truth_rank_global": truth_rank_global,
            "truth_rank_ours": truth_rank_ours,
            "rank1_global": g_label,
            "rank1_global_score": global_top["score"] if global_top else None,
            "rank1_ours": o_label,
            "rank1_ours_score": our_top["score"] if our_top else None,
            "ok_global": same_item,
            "ok_ours": truth_rank_ours == 1,
            "wrong_same_type": bool(same_type_diff_inst),
        }
        results.append(rec)
        status = "OK" if same_item else "MISS"
        detail = ""
        if not same_item:
            if same_type_diff_inst:
                detail = f" SAME_TYPE_DIFF_INSTANCE -> {g_label}"
            else:
                detail = f" DIFFERENT_ITEM -> {g_label}"
        print(
            f"{status} {row['label']}: rank1={g_label} ({rec['rank1_global_score']}) "
            f"truth_rank={truth_rank_global}{detail}"
        )

    ok = sum(1 for r in results if r["ok_global"])
    miss = [r for r in results if not r["ok_global"]]
    same_type_miss = [r for r in miss if r["wrong_same_type"]]
    other_miss = [r for r in miss if not r["wrong_same_type"]]
    ok_ours = sum(1 for r in results if r["ok_ours"])

    print("\n=== SUMMARY", MODEL_TAG, "===")
    print(f"queries: {len(results)}")
    print(f"rank1 correct (global): {ok}/{len(results)}")
    print(f"rank1 correct (among this run's founds only): {ok_ours}/{len(results)}")
    print(f"misses same-type different instance: {len(same_type_miss)}")
    for r in same_type_miss:
        print(f"  {r['query']} -> rank1 {r['rank1_global']} score={r['rank1_global_score']} truth_rank={r['truth_rank_global']}")
    print(f"misses different item/type: {len(other_miss)}")
    for r in other_miss:
        print(f"  {r['query']} -> rank1 {r['rank1_global']} score={r['rank1_global_score']} truth_rank={r['truth_rank_global']}")

    out = {
        "model": MODEL_TAG,
        "n": len(results),
        "rank1_ok_global": ok,
        "rank1_ok_ours": ok_ours,
        "results": results,
    }
    out_path = os.path.join(os.path.dirname(__file__), f"_eval_rank1_{MODEL_TAG.replace('/', '-')}.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
