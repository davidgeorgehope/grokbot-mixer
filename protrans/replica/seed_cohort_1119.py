#!/usr/bin/env python3
"""2026-11-19: pre-seed a flag arm's cohort score checkpoint with the floor's (cb1119_base) rows for cohort pairs whose engine family windows
are identical under that arm (thin_detect_1119 output) -- identical windows give the identical render, so only changed pairs are re-rendered.
Seeded rows carry seeded_from. usage: seed_cohort_1119.py DETECT.json ARM VARIANT_TAG"""
import os, sys, json
H = os.path.dirname(os.path.abspath(__file__)); P = os.path.dirname(H)
det, arm, tag = json.load(open(sys.argv[1])), sys.argv[2], sys.argv[3]
base = [json.loads(l) for l in open(os.path.join(P, 'results', 'score_ckpt', 'cb1119_base.jsonl'))]
p = os.path.join(P, 'results', 'score_ckpt', tag + '.jsonl'); have = {json.loads(l)['id'] for l in open(p)} if os.path.exists(p) else set()
n = 0
with open(p, 'a') as f:
    for r in base:
        o = det.get(r['id'])
        if r['id'] in have or not o or not o.get('base') or o.get(arm) != o['base']: continue
        f.write(json.dumps(dict(r, seeded_from='cb1119_base')) + '\n'); n += 1
print(tag, 'seeded', n, 'of', len(base))
