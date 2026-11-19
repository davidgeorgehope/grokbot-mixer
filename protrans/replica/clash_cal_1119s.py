#!/usr/bin/env python3
"""2026-11-19 day: re-run the two mix-only clash statistics (flam autocorrelation, off-grid onset share) with the new dev renders
(et1119c, et1119k, and safeplace renders if present) folded in as extra clean / injected (+60 ms, +110 ms incoming) cases.
Same rules as the nightly: threshold = pro p95 over the 33 pro clips (LOO FA), design picked on DEV injected cases only,
split = md5(pair id) % 3 (same pair -> same split across variants). No hand loosening. Writes clash_cal_1119s.json."""
import json, os, sys, pickle, numpy as np
from scipy.signal import resample_poly
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import clash_flam_1119 as F, clash_grid_1119 as G, picker_1119 as P
HOLD = set(P.HOLD); NEWV = [v for v in ('et1119c', 'et1119k', 'sp1119a', 'sp1119b') if os.path.exists(os.path.join(H, 'gate_ckpt', v + '.jsonl'))]
def new_cases():
    p = os.path.join(H, 'hc2_cache', 'clash_s_cases.pkl'); C = pickle.load(open(p, 'rb')) if os.path.exists(p) else {}
    cw = os.getcwd(); os.chdir(F.SRC2); import blend_diag as BD
    for v in NEWV:
        for l in open(os.path.join(H, 'gate_ckpt', v + '.jsonl')):
            r = json.loads(l); pid = r['id']
            if r.get('error') or r.get('dj') in HOLD or f'{v}:{pid}|clean' in C: continue
            M = json.load(open(r['meta'])); t = M['trans'][0]; s0, A, B = BD.crop_decks(M, 0)
            s, ee = int(float(t['start_bar']) - s0), int(float(t['end_bar']) - s0)
            for kind, ms in (('clean', 0), ('clash60', 60), ('clash110', 110)):
                k = int(ms / 1000 * 44100); BB = B if not k else np.concatenate([np.zeros((k, 2), np.float32), B[:-k]])
                y = resample_poly((A + BB).mean(1), 1, 2); f = F.feats(y, s, ee); f.update(kind=kind, split=F.split_of(pid), env=F.env(y), ee=ee, src=v)
                C[f'{v}:{pid}|{kind}'] = f
            pickle.dump(C, open(p, 'wb')); print('case', v, pid, flush=True)
    for f in C.values():  # repair cache rows written by the first run (env stored under 'e')
        if 'env' not in f: f['env'] = f['e']; f['e'] = f['ee']
    os.chdir(cw); return C
def p95(v): return float(np.percentile(v, 95))
def evaluate(pro_vals, case_vals, cases):
    th = p95(pro_vals); fa = float(np.mean([pro_vals[j] > p95([x for i, x in enumerate(pro_vals) if i != j]) for j in range(len(pro_vals))]))
    r = dict(thr=round(th, 4), pro_fa_loo=round(fa, 3), n_cases=len(cases))
    for sp in ('dev', 'heldout'):
        for kind in ('clean', 'clash60', 'clash110'):
            v = [case_vals[k] > th for k, f in cases.items() if f['split'] == sp and f['kind'] == kind]; r[f'{sp}_{kind}'] = round(float(np.mean(v)), 3) if v else None
    return r
if __name__ == '__main__':
    pros = F.pro_all(); old = F.cases_all(); NC = new_cases(); E = G.envs()
    flam_cases = {**{k: v for k, v in old.items()}, **NC}; out = dict(new_variants=NEWV, n_new_cases=len(NC), flam=[], grid=[])
    for lo, hi in ((35, 140), (45, 130), (50, 125), (35, 100), (90, 140)):
        for form in ('median', 'p75'):
            ps = [F.stat(f, lo, hi, form) for f in pros.values()]; cv = {k: F.stat(f, lo, hi, form) for k, f in flam_cases.items()}
            r = dict(lo=lo, hi=hi, form=form, **evaluate(ps, cv, flam_cases)); out['flam'].append(r); print('flam', r, flush=True)
    grid_cases = {**E['cases'], **{k: dict(e=f['env'], s=f['s'], ee=f['ee'], kind=f['kind'], split=f['split']) for k, f in NC.items()}}
    for tol in (12, 18, 25):
        for form in ('median', 'p25'):
            ps = [G.clip_stat(f['e'], f['s'], f['ee'], tol, form) for f in E['pro'].values()]; cv = {k: G.clip_stat(f['e'], f['s'], f['ee'], tol, form) for k, f in grid_cases.items()}
            r = dict(tol=tol, form=form, **evaluate(ps, cv, grid_cases)); out['grid'].append(r); print('grid', r, flush=True)
    for k in ('flam', 'grid'):
        ok = [r for r in out[k] if (r['dev_clean'] or 0) <= 0.05] or out[k]
        out[f'{k}_chosen_on_dev'] = max(ok, key=lambda r: ((r['dev_clash60'] or 0) + (r['dev_clash110'] or 0)) / 2 - (r['dev_clean'] or 0))
    out['meets_80pct_recall'] = any(min(out[f'{k}_chosen_on_dev'].get('heldout_clash60') or 0, out[f'{k}_chosen_on_dev'].get('heldout_clash110') or 0) >= 0.8 for k in ('flam', 'grid'))
    json.dump(out, open(os.path.join(H, 'clash_cal_1119s.json'), 'w'), indent=1); print('CHOSEN', out['flam_chosen_on_dev'], out['grid_chosen_on_dev'], 'meets80', out['meets_80pct_recall'])
