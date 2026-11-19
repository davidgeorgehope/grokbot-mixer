#!/usr/bin/env python3
"""2026-11-19: head-to-head of PLACE=safe variants on the same dev pairs (picks made leave-one-DJ-out), paired per pair,
95% CIs from a bootstrap that resamples whole mixes (4000 draws, seed 20261119). usage: safeplace_cmp_1119.py X Y  (e.g. c b)"""
import json, os, sys, numpy as np
H = os.path.dirname(os.path.abspath(__file__))
X, Y = sys.argv[1], sys.argv[2]
PX = {p['id']: p for p in json.load(open(os.path.join(H, f'safeplace_{X}_eval.json')))['pairs']}
PY = {p['id']: p for p in json.load(open(os.path.join(H, f'safeplace_{Y}_eval.json')))['pairs']}
ids = sorted(set(PX) & set(PY)); mixes = sorted({PX[i]['mix'] for i in ids}); rng = np.random.default_rng(20261119)
def fail(p, arm): return float(bool(p.get(f'{arm}_A')) or bool(p.get(f'{arm}_B')))
def ci(vals):
    by = {}
    for i, v in zip(ids, vals): by.setdefault(PX[i]['mix'], []).append(v)
    G = [np.array(by[m]) for m in mixes]; d = float(np.mean(vals)); bs = []
    for _ in range(4000):
        s = [G[j] for j in rng.integers(0, len(G), len(G))]; bs.append(np.concatenate(s).mean())
    lo, hi = np.percentile(bs, [2.5, 97.5]); v = 'better' if hi < 0 else 'worse' if lo > 0 else 'no clear difference'
    return dict(delta=round(d, 3), ci=[round(float(lo), 3), round(float(hi), 3)], verdict=f'{X} {v}' if v != 'no clear difference' else v)
out = dict(n=len(ids), n_mixes=len(mixes))
for arm in ('raw', 'final'):
    out[f'{X}_{arm}_any'] = round(float(np.mean([fail(PX[i], arm) for i in ids])), 3); out[f'{Y}_{arm}_any'] = round(float(np.mean([fail(PY[i], arm) for i in ids])), 3)
    out[f'{arm}_{X}_minus_{Y}'] = ci([fail(PX[i], arm) - fail(PY[i], arm) for i in ids])
out['default_any'] = round(float(np.mean([fail(PX[i], 'def') for i in ids])), 3)
out['same_final_window'] = int(sum(PX[i].get('final_win') == PY[i].get('final_win') for i in ids))
dj = {}
for i in ids:
    d = dj.setdefault(PX[i]['dj'], dict(n=0, default=0, **{f'{X}_final': 0, f'{Y}_final': 0, f'{X}_raw': 0, f'{Y}_raw': 0}))
    d['n'] += 1; d['default'] += int(fail(PX[i], 'def'))
    for arm in ('raw', 'final'): d[f'{X}_{arm}'] += int(fail(PX[i], arm)); d[f'{Y}_{arm}'] += int(fail(PY[i], arm))
out['per_dj'] = dj
json.dump(out, open(os.path.join(H, f'safeplace_cmp_{X}_vs_{Y}.json'), 'w'), indent=1); print(json.dumps({k: v for k, v in out.items() if k != 'per_dj'}))
