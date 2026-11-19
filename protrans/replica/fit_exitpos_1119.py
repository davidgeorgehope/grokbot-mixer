#!/usr/bin/env python3
"""2026-11-19 EXITPOS fit (see halftime/exitpos.py). Dev transitions (sections from corpus features). For each: the pro's window
(A gone at pro_out-1+overlap, B entered at pro_in-1) vs every grid alternative with the same overlap: A gone at any multiple of 8 from 32 bars
to its music end (and the music end itself), B entered at any multiple of 8 from 0 to 128. Conditional logit (softmax over the pair's
candidates), L2 1.0. Leave-one-DJ-out: per-DJ held-out log-lik and top-1 exit error; per-track weights exclude every DJ that played the
track. scale = STRUCTW(300) / (p95 - p5 of utility over dev candidates), so the term is as strong as the old bonus it replaces.
-> halftime/exitpos_w.json, exitpos_fit_1119.json"""
import os, sys, json, collections
import numpy as np
import scipy.optimize as _so
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H); sys.path.insert(0, os.path.join(H, 'halftime'))
import safeplace_1119 as S, exitpos as E
K = len(E.FEATS)
def build(r):
    sa, sb = r['sa'], r['sb']; ov = max(4, int(round(float(r.get('pro_ov') or 16)))); po = int(round(float(r['pro_out']))) - 1; pi = int(round(float(r['pro_in']))) - 1
    me = sa['music_end']; nb = sb.get('n_bars') or sb['music_end']; pe = po + ov
    C = [(pe, pi)]
    for e in sorted(set(range(32, me + 1, 8)) | {me}):
        for ib in range(0, min(129, nb - ov), 8):
            if abs(e - pe) <= 4 and abs(ib - pi) <= 4: continue
            C.append((e, ib))
    X = np.array([[E.feats(sa, sb, e, ib, ov)[k] for k in E.FEATS] for e, ib in C], float)
    return dict(id=r['id'], dj=r['dj'], mix=r['mix'], ya=r.get('ya'), X=X, C=C, ov=ov, me=me)
def nll(w, G, l2=1.0):
    t = 0.0; g = np.zeros(K)
    for d in G:
        z = d['X'] @ w; z -= z.max(); p = np.exp(z); p /= p.sum(); t -= np.log(p[0] + 1e-12); g -= d['X'][0] - p @ d['X']
    return t + l2 * w @ w, g + 2 * l2 * w
def fit(G):
    x, f, d = _so.fmin_l_bfgs_b(nll, np.zeros(K), args=(G,), approx_grad=False)
    return x
rows = [r for r in S.dev_rows() if r.get('pro_out') is not None and isinstance(r.get('sa'), dict) and isinstance(r.get('sb'), dict) and r['sa'].get('music_end')]
G = [build(r) for r in rows]; print('pairs', len(G), 'djs', len({g['dj'] for g in G}), 'mean cands', round(np.mean([len(g['C']) for g in G]), 1), flush=True)
wa = fit(G); allw = dict(coef=dict(zip(E.FEATS, map(float, wa))))
# leave-one-DJ-out held-out quality vs the rigid reference (A to music end, B drop at A's end) and vs uniform
lodo = {}; top_err = []; rig_err = []; ll = []; ll0 = []
for dj in sorted({g['dj'] for g in G}):
    w = fit([g for g in G if g['dj'] != dj]); lodo[dj] = dict(zip(E.FEATS, map(float, w)))
    for g in (g for g in G if g['dj'] == dj):
        z = g['X'] @ w; z -= z.max(); p = np.exp(z); p /= p.sum(); ll.append(float(np.log(p[0] + 1e-12))); ll0.append(-np.log(len(g['C'])))
        top = g['C'][int(np.argmax(g['X'] @ w))]; top_err.append(abs(top[0] - g['C'][0][0]))
        rig = [i for i, x in enumerate(g['X']) if not x.any()]  # reference window(s): all features 0
        rig_err.append(min(abs(g['C'][i][0] - g['C'][0][0]) for i in rig) if rig else np.nan)
U = np.concatenate([g['X'] @ wa for g in G]); scale = 300.0 / max(1e-6, float(np.percentile(U, 95) - np.percentile(U, 5)))
djs_of = collections.defaultdict(set)
for g in G: djs_of[g['ya']].add(g['dj'])
per_track = {}
for ya, djs in djs_of.items():
    if ya: per_track[ya] = dict(coef=dict(zip(E.FEATS, map(float, fit([g for g in G if g['dj'] not in djs])))))
json.dump(dict(all=allw, per_track=per_track, scale=scale, feats=list(E.FEATS), ref='fit_exitpos_1119 v1'), open(E.W_PATH, 'w'), indent=1)
rep = dict(n=len(G), coef_all=allw['coef'], scale=round(scale, 2), lodo_coef_sign_stable={k: len({np.sign(v[k]) for v in lodo.values()}) == 1 for k in E.FEATS},
           lodo_mean_ll=round(float(np.mean(ll)), 3), uniform_mean_ll=round(float(np.mean(ll0)), 3),
           lodo_top1_exit_err_bars_median=float(np.median(top_err)), rigid_exit_err_bars_median=float(np.nanmedian(rig_err)))
json.dump(dict(rep=rep, lodo=lodo), open(os.path.join(H, 'exitpos_fit_1119.json'), 'w'), indent=1)
print(json.dumps(rep, indent=1))
# guarded view (what the engine can actually pick): payoff guard v2 (A plays its last drop to its end, blend overlaps at most its last 32 bars) and
# cue guard (B enters at or before its first drop). Pairs whose pro window itself satisfies both; LODO weights.
def guard_ok(r, e, ib, ov):
    dr = r['sa'].get('drops') or [[0, 0]]; d1 = r['sb'].get('drop1')
    lde = dr[-1][1]; return e >= min(lde, r['sa']['music_end']) and e - ov >= lde - 32 and (d1 is None or ib <= d1)  # engine payoff guard v2
R = {r['id']: r for r in rows}; gres = []
for g in G:
    r = R[g['id']]; ok = [i for i, (e, ib) in enumerate(g['C']) if guard_ok(r, e, ib, g['ov'])]
    if 0 not in ok or len(ok) < 2: continue
    w = np.array([lodo[g['dj']][k] for k in E.FEATS]); u = g['X'][ok] @ w
    alt = [j for j, i in enumerate(ok) if i != 0]; top = g['C'][ok[alt[int(np.argmax(u[alt]))]]]  # best grid window (the pro's own entry would win ties)
    rig = [i for i in ok if not g['X'][i].any()]
    rig_e = min((g['C'][i] for i in rig), key=lambda c: abs(c[1] - g['C'][0][1]), default=None)
    gres.append(dict(id=g['id'], dj=g['dj'], mix=g['mix'], pro=g['C'][0], top=top, rig=rig_e, rank=int((u >= u[ok.index(0)]).sum()), n=len(ok)))
rep2 = dict(n_pro_within_guards=len(gres), share_of_pairs=round(len(gres) / len(G), 3),
            exit_err_model_median=float(np.median([abs(x['top'][0] - x['pro'][0]) for x in gres])),
            exit_err_rigid_median=float(np.median([abs(x['rig'][0] - x['pro'][0]) for x in gres if x['rig']])),
            cue_err_model_median=float(np.median([abs(x['top'][1] - x['pro'][1]) for x in gres])),
            cue_err_rigid_median=float(np.median([abs(x['rig'][1] - x['pro'][1]) for x in gres if x['rig']])),
            pro_rank_pct_median=float(np.median([x['rank'] / x['n'] for x in gres])))
json.dump(dict(rep=rep, guarded=rep2, guarded_rows=gres, lodo=lodo), open(os.path.join(H, 'exitpos_fit_1119.json'), 'w'), indent=1)
print('GUARDED', json.dumps(rep2))
