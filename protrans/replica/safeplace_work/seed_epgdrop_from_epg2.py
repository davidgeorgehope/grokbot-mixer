#!/usr/bin/env python3
"""Seed cs_epgdrop_1119 changed rows from cs_epg2_1119 when the window is identical."""
import json
from pathlib import Path
root = Path("/workspace/mixes/protrans")
det = json.load(open(root / "replica/epgdrop_detect_1119.json"))
src = root / "results/score_ckpt/cs_epg2_1119.jsonl"
dst = root / "results/score_ckpt/cs_epgdrop_1119.jsonl"
have = {json.loads(l)["id"] for l in open(dst)} if dst.exists() else set()
n = 0
with open(dst, "a") as f:
    for l in open(src):
        r = json.loads(l)
        o = det.get(r["id"])
        if not o or r["id"] in have:
            continue
        if o.get("DROP") and o["DROP"] == r["pick"]["win"] and o["DROP"] != o.get("base"):
            f.write(json.dumps(dict(r, seeded_from="cs_epg2_1119")) + "\n")
            n += 1
print("cs_epgdrop_1119 seeded", n, "changed rows from cs_epg2_1119")
