"""2026-11-20 nightly: deck-to-deck clash statistic 'frac_off' = share of confident overlap bars (|lag| finite, xcorr r >= c)
whose |lag| > L ms; abstains (score 0) with < mb confident bars. Threshold = pro p95 on the 33 pro clips (leave-one-pro-out FA);
never hand-set. Design (c, mb, L) chosen on the DEV injected split only: max mean(clash60, clash110 recall) - clean, with
dev clean <= 5% and pro LOO FA <= 10%. Held-out split (md5 % 3) reported afterwards. Cached arrays only (hc2_cache/cases_b, pro_b).
Diagnosis behind it: v2 median-lag fails because the pro p95 of the median (106 ms) is above the injected 60 ms clashes;
pro clips are measured on full mix audio so their median lag is noisy. A share-of-bars statistic is robust to that tail."""
import pickle, json, os, numpy as np, itertools
H = os.path.dirname(os.path.abspath(__file__))
CB = pickle.load(open(os.path.join(H, 'hc2_cache/cases_b.pkl'), 'rb')); PB = pickle.load(open(os.path.join(H, 'hc2_cache/pro_b.pkl'), 'rb'))
def score(a, c, mb, L):
    lag, r = np.abs(a['lag']), a['xr']; m = (r >= c) & np.isfinite(lag); m[:a['s']] = False; m[a['e']:] = False
    return float(np.mean(lag[m] > L)) if m.sum() >= mb else 0.0
rows = []
for c, mb, L in itertools.product((0.1, 0.15, 0.2, 0.25, 0.3), (3, 4, 5, 6, 8), (30, 40, 50)):
    ps = [score(f, c, mb, L) for f in PB.values()]; th = float(np.percentile(ps, 95))
    fa = float(np.mean([ps[j] > np.percentile([x for i, x in enumerate(ps) if i != j], 95) for j in range(len(ps))]))
    r = dict(c=c, mb=mb, L=L, thr=round(th, 3), pro_fa_loo=round(fa, 3))
    for sp in ('dev', 'heldout'):
        for k in ('clean', 'clash60', 'clash110', 'hole4', 'pump'):
            r[f'{sp}_{k}'] = round(float(np.mean([score(f, c, mb, L) > th for f in CB.values() if f['split'] == sp and f['kind'] == k])), 3)
    rows.append(r)
ok = [r for r in rows if r['dev_clean'] <= 0.05 and r['pro_fa_loo'] <= 0.10]
best = max(ok, key=lambda r: (r['dev_clash60'] + r['dev_clash110']) / 2 - r['dev_clean'])
json.dump(dict(rows=rows, chosen_on_dev=best, rule=__doc__), open(os.path.join(H, 'clash_frac_1120.json'), 'w'), indent=1)
print('CHOSEN', best)
