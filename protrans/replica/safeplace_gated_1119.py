#!/usr/bin/env python3
"""2026-11-19: render-gated PLACE=safe ("don't fix what isn't broken"): play the engine default; only when the rendered default fails
HC_A/HC_B use the variant's rank-1 pick (if it passes), else its rank-2 (if it passes), else the default. On dev this needs no new renders:
it is read from safeplace_<T>_eval.json. Mix-grouped bootstrap CIs (4000, seed 20261119). usage: safeplace_gated_1119.py T"""
import os, sys, json, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); T = sys.argv[1]
E = json.load(open(os.path.join(H, f'safeplace_{T}_eval.json')))['pairs']; Q = {x['id']: x for x in json.load(open(os.path.join(H, 'placequal_1119.json')))['rows']}
rows = []
for p in E:
    dfail = bool(p['def_A'] or p['def_B'])
    g = (bool(p['final_A'] or p['final_B']), p['final_win']) if dfail else (False, p['def_win'])
    rows.append(dict(id=p['id'], mix=p['mix'], dj=p['dj'], def_fail=dfail, g_fail=g[0], g_win=g[1], changed=g[1] != p['def_win'], v_fail=bool(p['final_A'] or p['final_B'])))
mixes = sorted({r['mix'] for r in rows}); rng = np.random.default_rng(20261119)
def ci(vals):
    by = {}
    for r, v in zip(rows, vals): by.setdefault(r['mix'], []).append(v)
    G = [np.array(by[m]) for m in mixes]; bs = [np.concatenate([G[j] for j in rng.integers(0, len(G), len(G))]).mean() for _ in range(4000)]
    lo, hi = np.percentile(bs, [2.5, 97.5]); return dict(delta=round(float(np.mean(vals)), 3), ci=[round(float(lo), 3), round(float(hi), 3)])
out = dict(variant=T, n=len(rows), n_mixes=len(mixes), default_fail=round(np.mean([r['def_fail'] for r in rows]), 3), gated_fail=round(np.mean([r['g_fail'] for r in rows]), 3),
           variant_final_fail=round(np.mean([r['v_fail'] for r in rows]), 3), gated_minus_default=ci([r['g_fail'] - r['def_fail'] for r in rows]),
           changed=int(sum(r['changed'] for r in rows)), changed_share=round(np.mean([r['changed'] for r in rows]), 3))
# leave-one-DJ-out stability of the gain
out['lodo_delta_range'] = [round(min(np.mean([r['g_fail'] - r['def_fail'] for r in rows if r['dj'] != d]) for d in {r['dj'] for r in rows}), 3),
                           round(max(np.mean([r['g_fail'] - r['def_fail'] for r in rows if r['dj'] != d]) for d in {r['dj'] for r in rows}), 3)]
json.dump(dict(out, rows=rows), open(os.path.join(H, f'safeplace_gated_{T}.json'), 'w'), indent=1); print(json.dumps(out))
