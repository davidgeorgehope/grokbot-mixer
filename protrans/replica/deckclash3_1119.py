#!/usr/bin/env python3
"""2026-11-19 day v3 per-deck clash check (flag HC_DECKCLASH=1, research; rules.json untouched).
Lessons from deckdrift_1119: (1) the 'clean' 168 ms tail of v2 was mostly a measurement artifact: the bass-swap EQ mutes one deck's
kick band during the overlap, and the bar-folded overlap profile then locks to the snare half a beat away; (2) per bar, a minority of
decks show REAL slow grid drift (20-40 ms over a 16-32 bar overlap) from the source's tempo/grid wandering vs the constant bar grid.
v3: measure on RAW decks (same bar map and nudges; crossfader gain, EQ lanes, drum swap, graph-cut removed: gains only, timing identical),
per bar (xcorr of that bar vs the deck's own solo template, +-120 ms, gated by r), deck lag = median(B bars) - median(A bars) over the
overlap ('med'), or the worse of the two overlap halves ('half', catches growing drift). Renders twice: engine as is (FP0) and with the
existing per-phrase re-sync finephase.py on (FINE_PHASE=1, FP1). Planted B shifts +60/+110/-60 ms inside the overlap only.
Threshold chosen on md5%3 dev split (clean <= 5%), reported on held-out, separately for FP0 and FP1. usage: deckclash3_1119.py [NMAX_PER_VAR]"""
import json, os, sys, pickle, hashlib, copy, numpy as np
from multiprocessing import Pool
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import deckclash_1119 as D1, deckclash2_1119 as D2, deckdrift_1119 as DD
CP = os.path.join(H, 'hc2_cache', 'deckclash3_env.pkl'); FPB = D2.FPB
def job(a):
    key, meta = a; os.chdir(D2.SRC2); import blend_diag as BD, finephase as FP
    out = {}
    try:
        M = json.load(open(meta)); t = M['trans'][0]
        for fp in ('0', '1'):
            os.environ['FINE_PHASE'] = fp; M2 = copy.deepcopy(M)
            for d in M2['decks'][:2]:
                d['auto'] = dict(gain=[[-1e6, 1.0], [1e6, 1.0]]); d.pop('dswap', None); d.pop('graphcut', None)
            s0, A, B = BD.crop_decks(M2, 0)
            out[f'eA{fp}'] = D1.kick_env(A).astype(np.float32); out[f'eB{fp}'] = D1.kick_env(B).astype(np.float32)
            if fp == '1':
                out['fp_nudge'] = {w: [FP.nudge_ms(M['decks'][j]['id'], sb) for sb, _ in M['decks'][j]['full_map']] for j, w in ((0, 'A'), (1, 'B'))}
        os.environ['FINE_PHASE'] = '0'
        out.update(s=int(float(t['start_bar']) - s0), e=int(float(t['end_bar']) - s0), n=int(min(len(A), len(B)) // D1.BS))
        return key, out
    except Exception as ex:
        os.environ['FINE_PHASE'] = '0'; return key, None
def deck_bars(c, fp, plant=None):
    n, s, e = c['n'], max(0, c['s']), min(c['n'], c['e']); ov = list(range(s, e)); soA = list(range(0, s)); soB = list(range(e, n))
    eA, eB = c[f'eA{fp}'].astype(float), c[f'eB{fp}'].astype(float)
    if plant is not None and ov: eB = D2.shift_env(eB, plant, int(ov[0] * FPB), int((ov[-1] + 1) * FPB))
    if len(soA) < 3 or len(soB) < 3 or len(ov) < 4: return None
    tA, tB = D1.fold_profile(eA, soA), D1.fold_profile(eB, soB)
    return ov, DD.per_bar(eA, ov, tA), DD.per_bar(eB, ov, tB)
def stat(bars, rmin, minb=3):
    if bars is None: return np.nan, np.nan
    ov, pA, pB = bars
    def med(P): v = [l for k, l, r in P if np.isfinite(l) and r >= rmin]; return (float(np.median(v)) if len(v) >= minb else np.nan)
    m = med(pB) - med(pA); h = len(ov) // 2
    hs = [med(pB[:h]) - med(pA[:h]), med(pB[h:]) - med(pA[h:])] if h >= 4 else [m]
    hs = [x for x in hs if np.isfinite(x)]; return m, (max(hs, key=abs) if hs else np.nan)
KINDS = {'clean': None, 'clash60': 60, 'clash110': 110, 'clashm60': -60}
if __name__ == '__main__':
    import picker_1119 as P
    NMAX = int(sys.argv[1]) if len(sys.argv) > 1 else 80; HOLD = set(P.HOLD)
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
            if i % 25 == 0: pickle.dump(E, open(CP, 'wb')); print(i, k, flush=True)
    pickle.dump(E, open(CP, 'wb'))
    RM = (0.1, 0.2, 0.3, 0.4); out = dict(n_renders=len(E))
    for fp in ('0', '1'):
        C = {}
        for k, c in E.items():
            b = {kd: deck_bars(c, fp, pl) for kd, pl in KINDS.items()}
            C[k] = dict(split=D1.split_of(k.split(':', 1)[1]), **{f'{kd}|{rm}': stat(b[kd], rm) for kd in KINDS for rm in RM})
            if fp == '0':
                tr = [DD.trend([p for p in P_ if True]) for P_ in (b['clean'][1], b['clean'][2])] if b['clean'] else []
                C[k]['trend'] = tr
        grid = []
        for si, sname in ((0, 'med'), (1, 'half')):
            for rm in RM:
                for Dm in range(10, 61, 2):
                    def rate(sp, kd):
                        v = [bool(np.isfinite(c[f'{kd}|{rm}'][si]) and abs(c[f'{kd}|{rm}'][si]) > Dm) for c in C.values() if c['split'] == sp]; return round(float(np.mean(v)), 3) if v else None
                    judged = round(float(np.mean([np.isfinite(c[f'clean|{rm}'][si]) for c in C.values()])), 3)
                    grid.append(dict(stat=sname, rmin=rm, D=Dm, judged=judged, **{f'{sp}_{kd}': rate(sp, kd) for sp in ('dev', 'heldout') for kd in KINDS}))
        ok = [g for g in grid if g['dev_clean'] <= 0.05]
        best = max(ok, key=lambda g: (min(g['dev_clash60'], g['dev_clash110'], g['dev_clashm60']), -g['D'])) if ok else None
        cm = np.array([c['clean|0.2'][0] for c in C.values() if np.isfinite(c['clean|0.2'][0])])
        out[f'FP{fp}'] = dict(clean_abs_p50=round(float(np.median(np.abs(cm))), 1), clean_abs_p90=round(float(np.percentile(np.abs(cm), 90)), 1), clean_abs_p95=round(float(np.percentile(np.abs(cm), 95)), 1),
                              clean_over20=round(float(np.mean(np.abs(cm) > 20)), 3), chosen_on_dev=best,
                              meets=bool(best and min(best['heldout_clash60'], best['heldout_clash110'], best['heldout_clashm60']) >= 0.8 and best['heldout_clean'] <= 0.05), grid=grid)
        if fp == '0':
            T = [t for c in C.values() for t in c.get('trend') or [] if t.get('n', 0) >= 6]
            out['drift_decks'] = dict(n=len(T), trend_span_over20_r2_over_0p5=int(sum(abs(t['span_ms']) > 20 and t['r2'] > 0.5 for t in T)), resid_sd_p50=round(float(np.median([t['resid_sd'] for t in T])), 1))
        print('FP' + fp, {k: v for k, v in out[f'FP{fp}'].items() if k != 'grid'}, flush=True)
    nz = [sum(abs(x) > 0 for x in c['fp_nudge'][w]) for c in E.values() for w in 'AB' if c.get('fp_nudge')]
    out['finephase_decks_with_any_nudge'] = round(float(np.mean([x > 0 for x in nz])), 3); out['drift_decks'] = out.get('drift_decks')
    json.dump(out, open(os.path.join(H, 'deckclash3_1119.json'), 'w'), indent=1, default=float)
    print('DONE', out['drift_decks'], 'finephase nudged decks', out['finephase_decks_with_any_nudge'])

def annotate(variant, rmin=0.1):
    """add 'deck_lag' (ms, per-bar median B - A on raw decks; NaN = abstain) to hc2_cache/arr_<variant>.pkl for final_eval HC_DECKCLASH=1"""
    p = os.path.join(H, 'hc2_cache', f'arr_{variant}.pkl'); A = pickle.load(open(p, 'rb'))
    G = {json.loads(l)['id']: json.loads(l) for l in open(os.path.join(H, 'gate_ckpt', variant + '.jsonl'))}
    for k, a in A.items():
        if 'deck_lag' in a or k not in G: continue
        _, c = job((k, G[k]['meta'])); a['deck_lag'] = D3stat(c, rmin) if c else np.nan
    pickle.dump(A, open(p, 'wb')); return A
def D3stat(c, rmin): return stat(deck_bars(c, '0'), rmin)[0]
