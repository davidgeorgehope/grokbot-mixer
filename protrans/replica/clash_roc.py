#!/usr/bin/env python3
"""Candidate clash statistics vs held-out injected clashes; threshold = pro p95 always (LOO pro false-alarm rate reported).
Writes clash_roc.json."""
import pickle, json, os, itertools, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); C = os.path.join(H, 'hc2_cache')
CB = pickle.load(open(f'{C}/cases_b.pkl', 'rb')); CC = pickle.load(open(f'{C}/cases_c.pkl', 'rb'))
PB = pickle.load(open(f'{C}/pro_b.pkl', 'rb')); PC = pickle.load(open(f'{C}/pro_c.pkl', 'rb'))
def lags(f, meas):
    if meas == 'deck2deck': return np.abs(f['lag']), f['xr']
    return np.abs(f['lagAM'] - f['lagBM']), np.fmin(f['rAM'], f['rBM'])
def stat(f, meas, form, c, D, mask):
    L, r = lags(f, meas); m = (r >= c) & np.isfinite(L); m[:f['s']] = False; m[f['e']:] = False
    if mask == 'aud': m &= f['aud']
    if form == 'median': return float(np.median(L[m])) if m.sum() >= 2 else 0.0
    if form == 'count': return float(((L > D) & m).sum())
    if form == 'p75': return float(np.percentile(L[m], 75)) if m.sum() >= 2 else 0.0
def p95(v): return float(np.percentile(v, 95))
rows = []
for meas_o, meas_p, form, c, D, mask in itertools.product(('deck2deck', 'vsmix'), ('deck2deck', 'vsmix'), ('median', 'p75', 'count'), (0.1, 0.2, 0.3), (20, 45), ('overlap', 'aud')):
    if form != 'count' and D != 20: continue
    Co = CB if meas_o == 'deck2deck' else CC; Pp = PB if meas_p == 'deck2deck' else PC
    ps = [stat(f, meas_p, form, c, D, mask) for f in Pp.values()]; th = p95(ps)
    fa = np.mean([ps[j] > p95([x for i, x in enumerate(ps) if i != j]) for j in range(len(ps))])
    res = dict(ours=meas_o, pro=meas_p, form=form, cmin=c, D=D if form == 'count' else None, mask=mask, thr=round(th, 1), pro_fa_loo=round(float(fa), 3))
    for split in ('dev', 'heldout'):
        for kind in ('clean', 'clash60', 'clash110'):
            v = [stat(f, meas_o, form, c, D, mask) > th for k, f in Co.items() if f['split'] == split and f['kind'] == kind]
            res[f'{split}_{kind}'] = round(float(np.mean(v)), 3)
    rows.append(res)
rows.sort(key=lambda r: -(r['dev_clash60'] + r['dev_clash110'] - 2*r['dev_clean']))
json.dump(rows, open(os.path.join(H, 'clash_roc.json'), 'w'), indent=1)
for r in rows[:15]: print(r)
