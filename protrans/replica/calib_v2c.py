#!/usr/bin/env python3
"""Clash detector v2c calibration (hole stays v2b). Same injected set / md5 split / pro p95 rule as calib_v2.py.
Grid on DEV only: D in (20,30,45,60) ms x cmin in (0.1,0.2,0.3) x audible rel (12 dB). Writes hardcheck_v2c_calib.json."""
import json, os, sys, pickle, itertools, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import calib_v2 as CV, hardcheck_v2 as V
C = CV.C; DS = (20, 30, 45, 60); CMINS = (0.1, 0.2, 0.3)

def pro_c():
    p = os.path.join(C, 'pro_c.pkl')
    if os.path.exists(p): return pickle.load(open(p, 'rb'))
    base = CV.pro_feats()
    import run_admitted_tune as T, score, paths, diagnose_gap as D
    PRO = json.load(open(os.path.join(H, 'protrans_decisions.json'))); bs = score.BAR_SEC * V.SR; out = {}
    for rec in T.load_recs():
        if rec['id'] not in base: continue
        d = PRO[rec['id']]; pro = score._load(rec['pro_clip']); dk = []
        for side, yt in (('a', rec['a']['yt']), ('b', rec['b']['yt'])):
            lc = d['loc'][side]; z = D.place_source(os.path.join(paths.LIB, yt + '.m4a'), lc['track_t'], lc['mix_t'], len(pro)); z, _ = D.refine_lag(pro, z); dk.append(z)
        f = dict(base[rec['id']]); f.update(V.clash_feats_c(dk[0], dk[1], pro, bs, score.BAR_SEC/4, f['n'])); out[rec['id']] = f
        print('pro', rec['id'], flush=True)
    pickle.dump(out, open(p, 'wb')); return out

def cases_c():
    p = os.path.join(C, 'cases_c.pkl'); cases = pickle.load(open(p, 'rb')) if os.path.exists(p) else {}
    base = pickle.load(open(os.path.join(C, 'cases_b.pkl'), 'rb'))
    os.chdir(CV.SRC2); import blend_diag as BD
    from engine import BS, BAR
    rows = [json.loads(l) for l in open(os.path.join(H, 'gate_ckpt', 'default.jsonl'))]
    for r in rows:
        pid = r['id']
        if f'{pid}|clean' in cases: continue
        M = json.load(open(r['meta'])); s0, A, B = BD.crop_decks(M, 0)
        for kind, ms in (('clean', 0), ('clash60', 60), ('clash110', 110)):
            k = int(ms/1000*V.SR); BB = np.concatenate([np.zeros((k, 2), np.float32), B[:len(B)-k]]) if k else B
            f = dict(base[f'{pid}|{kind}']); f.update(V.clash_feats_c(A, BB, A + BB, BS, BAR/4, f['n'])); cases[f'{pid}|{kind}'] = f
        pickle.dump(cases, open(p, 'wb')); print('case', pid, flush=True)
    return cases

def ev(cases, pros, D, cmin, split):
    ps = [V.clash_score_c(f, f['aud'], D, cmin) for f in pros.values()]; th = CV.p95(ps)
    fa = sum(ps[j] > CV.p95([x for i, x in enumerate(ps) if i != j]) for j in range(len(ps))) / len(ps)
    res = dict(D=D, cmin=cmin, thr=th, pro_fa_loo=round(fa, 3), pro_scores={str(int(a)): int(b) for a, b in zip(*np.unique(ps, return_counts=True))})
    for kind in ('clean', 'clash60', 'clash110'):
        v = [V.clash_score_c(f, f['aud'], D, cmin) > th for f in cases.values() if f['split'] == split and f['kind'] == kind]
        res[kind] = dict(n=len(v), flag_rate=round(float(np.mean(v)), 3))
    return res

if __name__ == '__main__':
    pros = pro_c(); cases = cases_c(); best = None; grid = []
    for D, cm in itertools.product(DS, CMINS):
        r = ev(cases, pros, D, cm, 'dev'); grid.append(r)
        key = ((r['clash60']['flag_rate'] + r['clash110']['flag_rate']) / 2 - r['clean']['flag_rate'], -r['pro_fa_loo'])
        if best is None or key > best[0]: best = (key, D, cm)
    out = dict(chosen=dict(D=best[1], cmin=best[2]), dev=ev(cases, pros, best[1], best[2], 'dev'), heldout=ev(cases, pros, best[1], best[2], 'heldout'), dev_grid=grid)
    json.dump(out, open(os.path.join(H, 'hardcheck_v2c_calib.json'), 'w'), indent=1, default=lambda x: x.item() if hasattr(x, 'item') else str(x))
    print(json.dumps({k: out[k] for k in ('chosen', 'dev', 'heldout')}, indent=1, default=lambda x: x.item() if hasattr(x, 'item') else str(x)))
