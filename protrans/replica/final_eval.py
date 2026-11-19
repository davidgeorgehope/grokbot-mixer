#!/usr/bin/env python3
"""Final counting + DEV evaluation with recalibrated hard checks (2026-11-18 late night).
Hard-check sets (all thresholds = pro p95 on the 33 protrans pros; nothing hand-set):
  HC_A: v2 bass hole (area over T0=30 dB, thr from hardcheck_v2_calib.json) OR v1 beat clash OR half-beat OR v1 pumping
  HC_B: v2 bass hole OR v2 clash (median |deck-to-deck onset lag| over overlap bars with r>=0.3, thr = pro p95 from
        clash_roc.json) OR half-beat OR v1 pumping
Arms: default D, gated G, REPLICA=1 O, drop-exit X, drop-cue C. Policies: online_rule (K=3 / all earlier transitions),
LODO selector over arms (train hard-fail rate within 5 points of default). DEV only unless --fresh (KushSessions #303, once).
Writes final_eval_dev.json / final_eval_fresh.json."""
import json, os, sys, pickle, collections, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import hardcheck_v2 as V, policy as PO, online_style as OS, analyze as A, eval_gate as EG
CAL = json.load(open(os.path.join(H, 'hardcheck_v2_calib.json'))); HOLE_T0, HOLE_TH = CAL['chosen']['T0'], CAL['thresholds']['hole']
ROC = json.load(open(os.path.join(H, 'clash_roc.json')))
CL = next(r for r in ROC if r['ours'] == 'deck2deck' and r['pro'] == 'deck2deck' and r['form'] == 'median' and r['cmin'] == 0.3 and r['mask'] == 'overlap')
ARMS = dict(D='default', G='gated', O='on', X='dropx', C='dropc')

def med_lag(a, c=0.3):
    L, r = np.abs(a['lag']), a['xr']; m = (r >= c) & np.isfinite(L); m[:a['s']] = False; m[a['e']:] = False
    return float(np.median(L[m])) if m.sum() >= 2 else 0.0

DECKCLASH_D = 52.0  # ms; deckclash3_1119 FP0 'med' rmin 0.1, chosen on the md5%3 dev split at clean <= 5% (held-out clean 7.4%, recall 57/83/75%)
def flags(a):
    h = V.hole_score(a['lows'], a['s'], a['e'], HOLE_T0); hv = a['hard_v1']; ml = med_lag(a)
    base = bool(hv.get('halfbeat_fail') or hv.get('pumping')); hole = h > HOLE_TH
    # HC_DECKCLASH=1 (2026-11-19 day, research, off by default): per-deck kick lag from deckclash3_1119.annotate (raw decks, per bar, dev-chosen D)
    dc = bool(os.environ.get('HC_DECKCLASH') == '1' and a.get('deck_lag') is not None and np.isfinite(a['deck_lag']) and abs(a['deck_lag']) > DECKCLASH_D)
    return dict(hole_score=round(h, 1), med_lag=round(ml, 1), hole_v2=hole, clash_v1=bool(hv.get('beat_clash')), clash_v2=ml > CL['thr'],
                halfbeat=bool(hv.get('halfbeat_fail')), pump=bool(hv.get('pumping')), v1=bool(hv['hard_fail']), deckclash=dc,
                HC_A=bool(hole or hv.get('beat_clash') or base or dc), HC_B=bool(hole or ml > CL['thr'] or base or dc))

def arr(v):
    p = os.path.join(H, 'hc2_cache', f'arr_{v}.pkl'); return {k: flags(a) for k, a in pickle.load(open(p, 'rb')).items()} if os.path.exists(p) else {}

def attach(rs, pref, HC):
    for k, v in ARMS.items():
        rows = A.load(pref + v); F = arr(pref + v)
        for r in rs:
            x = rows.get(r['id'])
            if x is None or x.get('error') or r['id'] not in F: r[k] = None; continue
            x = dict(x); x['flags'] = F[r['id']]; x['hard'] = dict(hard_fail=F[r['id']][HC]); r[k] = x
    return [r for r in rs if all(r.get(k) for k in ARMS)]

def hf(tr, k): return float(np.mean([r[k]['hard']['hard_fail'] for r in tr]))
def te(tr, k): return float(np.mean([A.metric(r[k], 'exit_cue') for r in tr]))
def select(tr):
    ok = [k for k in ARMS if hf(tr, k) <= hf(tr, 'D') + 0.05]; return min(ok, key=lambda k: te(tr, k))

def choices(rs, train=None):
    """dict policy -> rows. train None = leave-one-DJ-out within rs (DEV); else fit on train (fresh)."""
    ch = collections.defaultdict(list); order = []; picks = {}
    for K in (3, 0):
        st, prior = OS.make_style(OS.history(), K)
        on = [len(prior(r)) >= 2 and st(r) > 0.5 for r in rs]
        ch[f'online_rule_K{K or "all"}'] = [r['O'] if u else r['D'] for r, u in zip(rs, on)]
        # added 23:55 after the DEV run above (exploratory, so labelled): same online style bit, drop windows as the mid-track arm
        ch[f'online_dropx_K{K or "all"}'] = [r['X'] if u else r['D'] for r, u in zip(rs, on)]
        ch[f'online_dropc_K{K or "all"}'] = [r['C'] if u else r['D'] for r, u in zip(rs, on)]
    groups = [(d, [r for r in rs if r['dj'] != d], [r for r in rs if r['dj'] == d]) for d in sorted({r['dj'] for r in rs})] if train is None else [('fresh', train, rs)]
    sel = {}
    for d, tr, tst in groups:
        k = select(tr); picks[d] = k
        for r in tst: sel[r['id']] = r[k]
    ch['lodo_select'] = [sel[r['id']] for r in rs]
    for a, v in ARMS.items(): ch[v] = [r[a] for r in rs]
    return ch, picks

def summarise(rs, ch):
    res = PO.evaluate(rs, ch); D = {r['id']: r['D'] for r in rs}
    for n, rows in ch.items():
        for hc in ('HC_A', 'HC_B', 'v1'):
            res[n][f'fails_{hc}'] = sum(x['flags'][hc] for x in rows)
        res[n]['new_fails_HC_A'] = [dict(id=r['id'], dj=r['dj'], win=x['win'], default_win=r['D']['win'], **{k: x['flags'][k] for k in ('hole_score', 'med_lag', 'hole_v2', 'clash_v1', 'clash_v2', 'halfbeat', 'pump')})
                                    for r, x in zip(rs, rows) if x['flags']['HC_A'] and not D[r['id']]['flags']['HC_A']]
        res[n]['fixed_HC_A'] = [r['id'] for r, x in zip(rs, rows) if not x['flags']['HC_A'] and D[r['id']]['flags']['HC_A']]
    return res

def fresh_rows():
    """KushSessions #303 rows built like policy.load_all"""
    PR = {r['id']: r for r in EG.pairs()}; Dk = A.load('kush_default'); rows = []
    for i in sorted(Dk):
        f, bnd, bndb = PO.feats(PR[i]['a'], PR[i]['b'])
        rows.append(dict(id=i, dj=Dk[i]['dj'], mix=Dk[i]['mix'], f=f, bnd=bnd, bndb=bndb, pro=PR[i]['pro'], same=False))
    return rows

if __name__ == '__main__':
    HC = os.environ.get('HC', 'HC_A'); out = dict(hard_check=HC, hole=dict(T0=HOLE_T0, thr=HOLE_TH), clash_v2=CL)
    dev = attach(PO.load_all(False), '', HC)
    for r in dev: r['same'] = r['D']['win'] == r['O']['win']
    if '--fresh' in sys.argv:
        fr = attach(fresh_rows(), 'kush_', HC)
        for r in fr: r['same'] = r['D']['win'] == r['O']['win']
        ch, picks = choices(fr, train=dev); out.update(n=len(fr), picks=picks, results=summarise(fr, ch)); name = 'final_eval_fresh.json'
    else:
        ch, picks = choices(dev); out.update(n=len(dev), picks=picks, results=summarise(dev, ch)); name = 'final_eval_dev.json'
        out['all103'] = {v: {hc: sum(f[hc] for f in arr(v).values()) for hc in ('v1', 'HC_A', 'HC_B', 'hole_v2', 'clash_v1', 'clash_v2', 'halfbeat', 'pump')} | dict(n=len(arr(v))) for v in ARMS.values()}
    json.dump(out, open(os.path.join(H, name), 'w'), indent=1, default=str)
    for n, s in out['results'].items():
        d = s.get('delta_vs_default', {}).get('exit_cue', {})
        print(f"{n:22s} exit_cue {s['exit_cue_mean']} d {d.get('delta')} {d.get('ci')} hit16 {s['exit_hit16']} cue16 {s['cue_hit16']} A {s['fails_HC_A']} B {s['fails_HC_B']} v1 {s['fails_v1']} new {[x['id'] for x in s['new_fails_HC_A']]}")
    print(out.get('picks')); print(json.dumps(out.get('all103'), indent=0))
