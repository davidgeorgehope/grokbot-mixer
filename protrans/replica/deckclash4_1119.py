#!/usr/bin/env python3
"""2026-11-19 day v4: HC_DECKCLASH recalibrated on REAL BAR_RESYNC=1 renders (engine flag; decks re-rendered from the same plans with
the gated per-bar re-sync on, raw decks = gain/EQ lanes off, timing identical). Set = the deck overlaps that drifted in deckclash3
(clean per-bar trend > 20 ms, R^2 > 0.5) + a clean random sample. Planted B shifts +60/+110/-60 ms inside the overlap only (after
re-sync). Disjoint split BY MIX (md5(mix) % 3 == 0 -> test): stat/rmin/D chosen on the calibration mixes (clean <= 5%), reported on
the test mixes. Also: how many bars the re-sync moved, and the drifting decks' trend before/after. usage: deckclash4_1119.py [N_CLEAN]"""
import json, os, sys, pickle, hashlib, copy, numpy as np
from multiprocessing import Pool
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import deckclash_1119 as D1, deckclash2_1119 as D2, deckclash3_1119 as D3, deckdrift_1119 as DD
CP = os.path.join(H, 'hc2_cache', 'deckclash4_env.pkl')
def job(a):
    key, meta = a; os.environ['BAR_RESYNC'] = '1'; os.chdir(D2.SRC2); import blend_diag as BD, engine
    try:
        M = json.load(open(meta)); t = M['trans'][0]; M2 = copy.deepcopy(M)
        for d in M2['decks'][:2]: d['auto'] = dict(gain=[[-1e6, 1.0], [1e6, 1.0]]); d.pop('dswap', None); d.pop('graphcut', None)
        engine._RESYNC_LOG.clear(); s0, A, B = BD.crop_decks(M2, 0); log = {k: dict(v) for k, v in engine._RESYNC_LOG.items()}
        return key, dict(eA0=D1.kick_env(A).astype(np.float32), eB0=D1.kick_env(B).astype(np.float32), moved=log,
                         s=int(float(t['start_bar']) - s0), e=int(float(t['end_bar']) - s0), n=int(min(len(A), len(B)) // D1.BS))
    except Exception as ex: return key, None
def mix_of(k): return k.split(':', 1)[1].rsplit('__', 1)[0]
def split_mix(k): return 'test' if int(hashlib.md5(mix_of(k).encode()).hexdigest(), 16) % 3 == 0 else 'cal'
def drifting(E3):
    out = set()
    for k, c in E3.items():
        b = D3.deck_bars(c, '0')
        if b is None: continue
        for P_ in (b[1], b[2]):
            t = DD.trend(P_)
            if t.get('n', 0) >= 6 and abs(t['span_ms']) > 20 and t['r2'] > 0.5: out.add(k)
    return out
if __name__ == '__main__':
    NC = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    E3 = pickle.load(open(D3.CP, 'rb')); DR = drifting(E3)
    rest = sorted([k for k in E3 if k not in DR], key=lambda k: hashlib.md5(('c' + k).encode()).hexdigest())[:NC]
    keys = sorted(DR) + rest; print('drifting renders', len(DR), 'clean sample', len(rest), flush=True)
    G = {}
    for k in keys:
        v = k.split(':', 1)[0]
        if v not in G: G[v] = {json.loads(l)['id']: json.loads(l) for l in open(os.path.join(H, 'gate_ckpt', v + '.jsonl'))}
    E = pickle.load(open(CP, 'rb')) if os.path.exists(CP) else {}
    todo = [(k, G[k.split(':', 1)[0]][k.split(':', 1)[1]]['meta']) for k in keys if k not in E]
    with Pool(3) as pool:
        for i, (k, c) in enumerate(pool.imap_unordered(job, todo)):
            if c is not None: E[k] = c
            if i % 20 == 0: pickle.dump(E, open(CP, 'wb')); print(i, k, flush=True)
    pickle.dump(E, open(CP, 'wb'))
    RM = (0.1, 0.2, 0.3); C = {}; moved = []; tr_before, tr_after = [], []
    for k in keys:
        if k not in E: continue
        c = E[k]; b = {kd: D3.deck_bars(c, '0', pl) for kd, pl in D3.KINDS.items()}
        C[k] = dict(split=split_mix(k), drift=k in DR, **{f'{kd}|{rm}': D3.stat(b[kd], rm) for kd in D3.KINDS for rm in RM})
        moved.append(sum(len(v) for v in c['moved'].values()))
        if k in DR:
            b0 = D3.deck_bars(E3[k], '0')
            if b0 and b['clean']:
                for P0, P1 in ((b0[1], b['clean'][1]), (b0[2], b['clean'][2])):
                    t0, t1 = DD.trend(P0), DD.trend(P1)
                    if t0.get('n', 0) >= 6 and abs(t0['span_ms']) > 20 and t0['r2'] > 0.5: tr_before.append(abs(t0['span_ms'])); tr_after.append(abs(t1.get('span_ms', np.nan)) if t1.get('n', 0) >= 6 else np.nan)
    grid = []
    for si, sname in ((0, 'med'), (1, 'half')):
        for rm in RM:
            for Dm in range(10, 61, 2):
                def rate(sp, kd): v = [bool(np.isfinite(c[f'{kd}|{rm}'][si]) and abs(c[f'{kd}|{rm}'][si]) > Dm) for c in C.values() if c['split'] == sp]; return round(float(np.mean(v)), 3) if v else None
                grid.append(dict(stat=sname, rmin=rm, D=Dm, **{f'{sp}_{kd}': rate(sp, kd) for sp in ('cal', 'test') for kd in D3.KINDS}))
    ok = [g for g in grid if g['cal_clean'] <= 0.05]; best = max(ok, key=lambda g: (min(g['cal_clash60'], g['cal_clash110'], g['cal_clashm60']), -g['D'])) if ok else None
    cm = np.array([c['clean|0.2'][0] for c in C.values() if np.isfinite(c['clean|0.2'][0])])
    out = dict(n=len(C), n_drifting=sum(c['drift'] for c in C.values()), n_cal=sum(c['split'] == 'cal' for c in C.values()), n_test=sum(c['split'] == 'test' for c in C.values()),
               n_cal_mixes=len({mix_of(k) for k, c in C.items() if c['split'] == 'cal'}), n_test_mixes=len({mix_of(k) for k, c in C.items() if c['split'] == 'test'}),
               renders_with_moved_bars=int(sum(m > 0 for m in moved)), moved_bars_total=int(sum(moved)),
               drift_decks=dict(n=len(tr_before), span_before_p50=round(float(np.median(tr_before)), 1) if tr_before else None, span_after_p50=round(float(np.nanmedian(tr_after)), 1) if tr_after else None,
                                still_over20=int(np.nansum([x > 20 for x in tr_after]))),
               clean_abs_p50=round(float(np.median(np.abs(cm))), 1), clean_abs_p90=round(float(np.percentile(np.abs(cm), 90)), 1), clean_abs_p95=round(float(np.percentile(np.abs(cm), 95)), 1),
               chosen_on_cal=best, meets=bool(best and min(best['test_clash60'], best['test_clash110'], best['test_clashm60']) >= 0.8 and best['test_clean'] <= 0.05), grid=grid)
    json.dump(out, open(os.path.join(H, 'deckclash4_1119.json'), 'w'), indent=1, default=float); print({k: v for k, v in out.items() if k != 'grid'})
