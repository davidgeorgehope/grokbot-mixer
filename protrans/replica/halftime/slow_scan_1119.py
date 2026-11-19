#!/usr/bin/env python3
"""2026-11-19: how often do pros vs we blend over slowdown / no-snare sections (slowdown.py)? Dev pairs (+ the protrans cohort reported apart).
Windows in each track's own bars: pro A = [pro_out-1, pro_out-1+overlap), pro B = [pro_in-1, ...); ours from the PLACE=safe eval files.
Per window: share of the outgoing blend bars inside an outgoing slowdown, does the blend start inside one, is it mostly (>= 50%) inside one,
the same for the incoming side, and which section type the outgoing slowdown is (intro / breakdown / outro / in-drop).
Mix-grouped bootstrap CIs (4000, seed 20261119) for pro minus default. -> slow_scan_1119.json"""
import os, sys, json, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); R = os.path.dirname(H); sys.path.insert(0, R); sys.path.insert(0, H)
import safeplace_1119 as S, slowdown as SD
SRC2 = '/workspace/mixes/src2'
def secs(yt):
    p = os.path.join(SRC2, 'st', yt + '.slowdown.json'); return json.load(open(p))['sections'] if os.path.exists(p) else None
def kind(sa, x, y):
    dr = sa.get('drops') or []
    if not dr: return 'unknown'
    if y <= dr[0][0] + 2: return 'intro'
    if x >= dr[-1][1] - 4: return 'outro'
    if any(a <= x and y <= b for a, b in dr): return 'in_drop'
    return 'breakdown'
def m(sec, a0, a1):
    if not sec or a1 <= a0: return dict(share=np.nan, start_in=np.nan, mostly=np.nan)
    sh = SD.overlap_frac(sec, a0, a1); st = float(any(x <= a0 < y for x, y in sec)); return dict(share=sh, start_in=st, mostly=float(sh >= 0.5))
def main():
    rows = {r['id']: r for r in S.B.build(S.P.rows_all(), S.P.load_rendered_defaults())}
    import run_admitted_tune as T
    REC = {r['id']: r for r in T.load_recs()}
    for k, r in rows.items():
        if 'ya' not in r:
            if k in REC: r['ya'], r['yb'] = REC[k]['a']['yt'], REC[k]['b']['yt']
            else:
                f = json.load(open(os.path.join(S.P0, 'corpus_v2', 'features', k + '.json'))); r['ya'], r['yb'] = f['track_a']['yt'], f['track_b']['yt']
    EV = {v: {p['id']: p for p in json.load(open(os.path.join(R, f'safeplace_{v}_eval.json')))['pairs']} for v in ('c', 'd')}
    G = {v: {x['id']: x for x in json.load(open(os.path.join(R, f'safeplace_gated_{v}.json')))['rows']} for v in ('c', 'd')}
    out = []
    for k, r in rows.items():
        sa_, sb_ = secs(r['ya']), secs(r['yb'])
        if sa_ is None or sb_ is None or r.get('pro_out') is None: continue
        ov = int(round(float(r.get('pro_ov') or 16))); po, pi = int(round(float(r['pro_out']))) - 1, int(round(float(r['pro_in']))) - 1
        W = {'pro': (po, po + ov, pi, pi + ov), 'default': None}
        dw = S.default_win(r); W['default'] = (dw[1] - dw[4], dw[1], dw[3], dw[3] + dw[4])
        for v in ('c', 'd'):
            if k in EV[v]: w = EV[v][k]['final_win']; W[f'{v}_final'] = (w[1] - w[4], w[1], w[3], w[3] + w[4])
            if k in G[v]: w = G[v][k]['g_win']; W[f'{v}_gated'] = (w[1] - w[4], w[1], w[3], w[3] + w[4])
        rec = dict(id=k, mix=r['mix'], dj=r['dj'], set=r['set'], slowA=sa_, slowB=sb_, A_kinds=[kind(r['sa'], x, y) for x, y in sa_])
        for nm, (a0, a1, b0, b1) in W.items():
            rec[nm] = dict(win=[a0, a1, b0, b1], A=m(sa_, a0, a1), B=m(sb_, b0, b1),
                           A_kind=next((kind(r['sa'], x, y) for x, y in sa_ if x <= a0 < y or (a0 <= x < a1)), None))
        out.append(rec)
    rng = np.random.default_rng(20261119)
    def agg(sel, nm, side, key):
        v = [x[nm][side][key] for x in sel if nm in x and np.isfinite(x[nm][side][key])]; return round(float(np.mean(v)), 3) if v else None
    def dci(sel, nm, side, key, base='default'):
        by = {}
        for x in sel:
            if nm in x and base in x and np.isfinite(x[nm][side][key]) and np.isfinite(x[base][side][key]): by.setdefault(x['mix'], []).append(x[nm][side][key] - x[base][side][key])
        if not by: return None
        Gm = list(map(np.array, by.values())); d = float(np.mean(np.concatenate(Gm))); bs = [np.concatenate([Gm[j] for j in rng.integers(0, len(Gm), len(Gm))]).mean() for _ in range(4000)]
        lo, hi = np.percentile(bs, [2.5, 97.5]); return dict(delta=round(d, 3), ci=[round(float(lo), 3), round(float(hi), 3)])
    res = {}
    for name, sel in (('dev', [x for x in out if x['set'] == 'dev']), ('dev_with_audio', [x for x in out if x['set'] == 'dev' and 'd_final' in x]), ('cohort', [x for x in out if x['set'] == 'protrans'])):
        arms = ['pro', 'default', 'c_final', 'd_final', 'c_gated', 'd_gated']
        res[name] = dict(n=len(sel), n_mixes=len({x['mix'] for x in sel}), outgoing_has_slowdown=round(float(np.mean([bool(x['slowA']) for x in sel])), 3) if sel else None,
                         means={a: {f'{s}_{k}': agg(sel, a, s, k) for s in 'AB' for k in ('share', 'start_in', 'mostly')} for a in arms},
                         pro_minus_default={f'{s}_{k}': dci(sel, 'pro', s, k) for s in 'AB' for k in ('share', 'start_in', 'mostly')},
                         A_kind_when_start_in={a: dict(__import__('collections').Counter(x[a]['A_kind'] for x in sel if a in x and x[a]['A']['start_in'] == 1)) for a in arms})
    json.dump(dict(res, rows=out), open(os.path.join(H, 'slow_scan_1119.json'), 'w'), indent=1, default=float); print(json.dumps(res, indent=1))
if __name__ == '__main__': main()
