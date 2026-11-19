"""2026-11-19 nightly: extend the v2 bass-hole T0 grid past 30 dB (cached arrays only, no renders). Threshold = pro p95 on the 33
pro clips (leave-one-pro-out FA). T0 chosen on the DEV injected split only (max mean(hole4, hole8) - clean, dev clean <= 5%);
held-out (md5 % 3) reported afterwards. Writes hole_t0_1119.json."""
import pickle, json, numpy as np, sys, os
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import hardcheck_v2 as V
CB = pickle.load(open(os.path.join(H, 'hc2_cache/cases_b.pkl'), 'rb')); PB = pickle.load(open(os.path.join(H, 'hc2_cache/pro_b.pkl'), 'rb'))
def p95(v): return float(np.percentile(v, 95))
rows = []
for T0 in range(24, 49, 2):
    ps = [V.hole_score(f['lows'], f['s'], f['e'], T0) for f in PB.values()]; th = p95(ps)
    fa = float(np.mean([ps[j] > p95([x for i, x in enumerate(ps) if i != j]) for j in range(len(ps))]))
    r = dict(T0=T0, thr=round(th, 1), pro_fa_loo=round(fa, 3))
    for sp in ('dev', 'heldout'):
        for k in ('clean', 'hole4', 'hole8', 'pump', 'clash60', 'clash110'):
            v = [V.hole_score(f['lows'], f['s'], f['e'], T0) > th for f in CB.values() if f['split'] == sp and f['kind'] == k]
            r[f'{sp}_{k}'] = round(float(np.mean(v)), 3); r[f'{sp}_n'] = len(v)
    rows.append(r)
ok = [r for r in rows if r['dev_clean'] <= 0.05]
best = max(ok, key=lambda r: (r['dev_hole4'] + r['dev_hole8']) / 2 - r['dev_clean'])
json.dump(dict(rows=rows, chosen_on_dev=best, rule=__doc__), open(os.path.join(H, 'hole_t0_1119.json'), 'w'), indent=1)
for r in rows: print(r)
print('CHOSEN', best)
