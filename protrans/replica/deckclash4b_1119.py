#!/usr/bin/env python3
"""2026-11-19 day v4b: why v4 missed, and a tiered rule. v4 showed that when the strict confidence gate (rmin 0.2) judges an overlap,
planted 60/110 ms clashes and clean overlaps separate cleanly, but it abstains on ~44% of overlaps, which caps recall at ~60%.
Tiered rule: use the strict stat (rmin r1) when it has >= 3 confident bars, else fall back to the loose stat (rmin r2) with its own,
larger threshold. Both thresholds chosen on the calibration mixes (clean <= 5%), reported on the disjoint test mixes (split by mix)."""
import os, sys, json, pickle, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import deckclash3_1119 as D3, deckclash4_1119 as D4
RC = os.path.join(H, 'hc2_cache', 'deckclash4b_stats.pkl')
E = pickle.load(open(D4.CP, 'rb')); R = pickle.load(open(RC, 'rb')) if os.path.exists(RC) else {}
for k, c in E.items():
    if k in R: continue
    R[k] = dict(split=D4.split_mix(k))
    for kd, pl in D3.KINDS.items():
        b = D3.deck_bars(c, '0', pl)
        for rm in (0.1, 0.15, 0.2): R[k][f'{kd}|{rm}'] = D3.stat(b, rm)[0]
def flag(r, kd, r1, d1, r2, d2):
    v = r[f'{kd}|{r1}']
    if np.isfinite(v): return abs(v) > d1
    v = r[f'{kd}|{r2}']; return bool(np.isfinite(v) and abs(v) > d2)
def rate(sp, kd, *p): v = [flag(r, kd, *p) for r in R.values() if r['split'] == sp]; return round(float(np.mean(v)), 3)
pickle.dump(R, open(RC, 'wb')); grid = []
for r1 in (0.15, 0.2):
    for d1 in range(14, 41, 2):
        for d2 in list(range(20, 131, 2)) + [1e9]:
            p = (r1, d1, 0.1, d2); grid.append(dict(r1=r1, D1=d1, r2=0.1, D2=d2, **{f'{sp}_{kd}': rate(sp, kd, *p) for sp in ('cal', 'test') for kd in D3.KINDS}))
ok = [g for g in grid if g['cal_clean'] <= 0.05]
best = max(ok, key=lambda g: (min(g['cal_clash60'], g['cal_clash110'], g['cal_clashm60']), -g['D1'], -g['D2']))
cov = {rm: round(float(np.mean([np.isfinite(r[f'clean|{rm}']) for r in R.values()])), 3) for rm in (0.1, 0.15, 0.2)}
out = dict(coverage_clean=cov, chosen_on_cal=best, meets=bool(min(best['test_clash60'], best['test_clash110'], best['test_clashm60']) >= 0.8 and best['test_clean'] <= 0.05), grid=grid)
json.dump(out, open(os.path.join(H, 'deckclash4b_1119.json'), 'w'), indent=1, default=float); print({k: v for k, v in out.items() if k != 'grid'})
