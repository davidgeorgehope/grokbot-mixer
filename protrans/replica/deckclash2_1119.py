#!/usr/bin/env python3
"""2026-11-19 day v2: per-deck SELF-REFERENCED clash check (flag HC_DECKCLASH=1, research, not in rules.json).
v1 (deckclash_1119.py) compared deck A's kick phase to deck B's: that mixes up 'out of time' with 'different drum pattern'
(clean renders sat at up to +-170 ms = half a beat). v2 compares each deck only with ITSELF: its bar-folded kick profile in its
own solo bars (A before the blend, B after) vs during the overlap, on the master bar grid. drift = driftB - driftA.
A deck that slips during the blend (stretch/placement/nudge error) shows up; drum-pattern differences cancel.
Planted: B shifted +60/+110/-60 ms only inside the overlap (envelope shift == audio shift for flux up to frame rounding).
Known blind spot, reported: a WHOLE-deck constant shift (a source beat-grid error) is invisible to this check by design.
Threshold chosen on md5%3 dev split (clean <= 5%), reported on held-out. usage: deckclash2_1119.py [NMAX_PER_VAR]"""
import json, os, sys, pickle, hashlib, numpy as np
from multiprocessing import Pool
H = os.path.dirname(os.path.abspath(__file__)); P0 = os.path.dirname(H); SRC2 = os.path.join(os.path.dirname(P0), 'src2')
for p in (P0, SRC2, H):
    if p not in sys.path: sys.path.insert(0, p)
import deckclash_1119 as D1
SR, HOP, BS = D1.SR, D1.HOP, D1.BS; FPB = BS / HOP
CP = os.path.join(H, 'hc2_cache', 'deckclash2_env.pkl')
def bars_db(y): return D1.bar_db(y, int(len(y) // BS))
def job(a):
    key, meta = a
    os.chdir(SRC2); import blend_diag as BD
    try:
        M = json.load(open(meta)); t = M['trans'][0]; s0, A, B = BD.crop_decks(M, 0)
    except Exception as ex: return key, None
    s, e = int(float(t['start_bar']) - s0), int(float(t['end_bar']) - s0)
    return key, dict(s=s, e=e, aA=bars_db(A), aB=bars_db(B), eA=D1.kick_env(A).astype(np.float32), eB=D1.kick_env(B).astype(np.float32))
def shift_env(e, ms, f0, f1):
    """shift envelope by ms (positive = later) only for frames [f0,f1)"""
    out = e.astype(float).copy(); k = ms / 1000 * SR / HOP; idx = np.arange(f0, min(f1, len(e)))
    out[idx] = np.interp(idx - k, np.arange(len(e)), e); return out
def measure(c, plant=None):
    n = min(len(c['aA']), len(c['aB'])); s, e = max(0, c['s']), min(n, c['e']); aA, aB = c['aA'][:n], c['aB'][:n]
    lA, lB = np.percentile(aA, 90) - 15, np.percentile(aB, 90) - 15
    ov = [k for k in range(s, e) if aA[k] > lA and aB[k] > lB] or list(range(s, e))
    soA = [k for k in range(0, s) if aA[k] > lA and aB[k] < lB] or [k for k in range(0, s) if aA[k] > lA]
    soB = [k for k in range(e, n) if aB[k] > lB and aA[k] < lA] or [k for k in range(e, n) if aB[k] > lB]
    if len(ov) < 4 or len(soA) < 3 or len(soB) < 3: return dict(drift=np.nan, r=0.0, lag=np.nan, xr=0.0)
    eA, eB = c['eA'].astype(float), c['eB'].astype(float)
    if plant is not None:
        ms, whole = plant; f0, f1 = (0, len(eB)) if whole else (int(min(ov) * FPB), int((max(ov) + 1) * FPB)); eB = shift_env(eB, ms, f0, f1)
    dA, rA = D1.xlag(D1.fold_profile(eA, soA), D1.fold_profile(eA, ov)); dB, rB = D1.xlag(D1.fold_profile(eB, soB), D1.fold_profile(eB, ov))
    xl, xr = D1.xlag(D1.fold_profile(eA, ov), D1.fold_profile(eB, ov))
    return dict(drift=dB - dA if np.isfinite(dA) and np.isfinite(dB) else np.nan, r=min(rA, rB), dA=dA, dB=dB, lag=xl, xr=xr)
KINDS = {'clean': None, 'clash60': (60, False), 'clash110': (110, False), 'clashm60': (-60, False), 'whole60': (60, True), 'whole110': (110, True)}
if __name__ == '__main__':
    import picker_1119 as P
    NMAX = int(sys.argv[1]) if len(sys.argv) > 1 else 70; HOLD = set(P.HOLD)
    E = pickle.load(open(CP, 'rb')) if os.path.exists(CP) else {}; todo = []
    for v in D1.VARS:
        rows = [json.loads(l) for l in open(os.path.join(H, 'gate_ckpt', v + '.jsonl'))]
        rows = [r for r in rows if not r.get('error') and r.get('dj') not in HOLD and r.get('src') != 'protrans']
        rows.sort(key=lambda r: hashlib.md5((v + r['id']).encode()).hexdigest())
        for r in rows[:NMAX]:
            k = f"{v}:{r['id']}"
            if k not in E: todo.append((k, r['meta']))
    print('todo', len(todo), 'cached', len(E), flush=True)
    with Pool(3) as pool:
        for i, (k, c) in enumerate(pool.imap_unordered(job, todo)):
            if c is not None: E[k] = c
            if i % 20 == 0: pickle.dump(E, open(CP, 'wb')); print(i, k, flush=True)
    pickle.dump(E, open(CP, 'wb'))
    C = {}
    for k, c in E.items():
        C[k] = dict(split=D1.split_of(k.split(':', 1)[1]), **{kd: measure(c, pl) for kd, pl in KINDS.items()})
    def flag(x, D, rmin): return bool(np.isfinite(x['drift']) and x['r'] >= rmin and abs(x['drift']) > D)
    def rate(sp, kd, D, rmin): v = [flag(c[kd], D, rmin) for c in C.values() if c['split'] == sp]; return round(float(np.mean(v)), 3) if v else None
    grid = []
    for rmin in (0, 0.2, 0.3, 0.4, 0.5, 0.6):
        for D in range(10, 61, 2):
            grid.append(dict(D=D, rmin=rmin, judged_dev=round(float(np.mean([c['clean']['r'] >= rmin and np.isfinite(c['clean']['drift']) for c in C.values() if c['split'] == 'dev'])), 3),
                             **{f'{sp}_{kd}': rate(sp, kd, D, rmin) for sp in ('dev', 'heldout') for kd in KINDS}))
    ok = [g for g in grid if g['dev_clean'] <= 0.05]
    best = max(ok, key=lambda g: (min(g['dev_clash60'], g['dev_clash110'], g['dev_clashm60']), -g['D'])) if ok else None
    cd = np.array([c['clean']['drift'] for c in C.values() if np.isfinite(c['clean']['drift'])]); cl = np.array([c['clean']['lag'] for c in C.values() if np.isfinite(c['clean']['lag'])])
    out = dict(n_renders=len(C), n_dev=sum(c['split'] == 'dev' for c in C.values()), n_heldout=sum(c['split'] == 'heldout' for c in C.values()),
               clean_drift_abs_p50=round(float(np.median(np.abs(cd))), 1), clean_drift_abs_p95=round(float(np.percentile(np.abs(cd), 95)), 1),
               v1_clean_deck_lag_abs_p50=round(float(np.median(np.abs(cl))), 1), v1_clean_deck_lag_abs_p95=round(float(np.percentile(np.abs(cl), 95)), 1),
               chosen_on_dev=best, meets=bool(best and min(best['heldout_clash60'], best['heldout_clash110'], best['heldout_clashm60']) >= 0.8 and best['heldout_clean'] <= 0.05), grid=grid)
    json.dump(out, open(os.path.join(H, 'deckclash2_1119.json'), 'w'), indent=1)
    print('CHOSEN', best, 'meets', out['meets'], {k: out[k] for k in list(out)[:7]})
