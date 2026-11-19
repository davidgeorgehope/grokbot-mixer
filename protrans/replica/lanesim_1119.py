#!/usr/bin/env python3
"""2026-11-19 day: the engine's REAL fader + EQ lanes for the risk simulation (PLACE=safe, research).
Templates: per blend length X in {16, 32}, the median over rendered dev blends of each lane (deck gain, low <150 Hz lane, high >2 kHz
lane, for A and B) sampled at the blend's bars (u = (k + 0.5) / X), taken from the render metas (what the engine actually played).
Sim per candidate window: per bar and deck, power = gain^2 * (low_lane^2 * P_low + P_mid + high_lane^2 * P_high) from the source per-bar
bands (st 'low', 'hat' as the high band, mid = all - low - hat), summed over decks. Features: full-band V-dip of the simulated sum
(same vdip as hardcheck 'pumping'), the low+high band V-dip, and the deepest bar vs the blend's first bar.
GAP constraint: simulated full-band vdip >= X_GAP dB (X_GAP = pro p95 of vdip, hardcheck_calib.json pump_p95) -> candidate dropped.
usage: lanesim_1119.py build   (writes safeplace_work/lane_templates.json)   |   lanesim_1119.py validate"""
import json, os, sys, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
WK = os.path.join(H, 'safeplace_work'); TP = os.path.join(WK, 'lane_templates.json')
X_GAP = float(json.load(open(os.path.join(H, 'hardcheck_calib.json')))['pump_p95'])
VARS = ['default', 'ndef1119', 'pick1119', 'et1119c', 'et1119k', 'sp1119a1', 'sp1119b1']
def interp(pts, t, dflt=1.0):
    if not pts: return np.full(len(t), dflt)
    p = np.array(pts, float); o = np.argsort(p[:, 0]); return np.interp(t, p[o, 0], p[o, 1])
def lanes_from_meta(M):
    t = M['trans'][0]; s, e = float(t['start_bar']), float(t['end_bar']); X = int(round(e - s)); tt = s + np.arange(X) + 0.5
    A, B = M['decks'][0]['auto'], M['decks'][1]['auto']
    return X, {k: interp(d.get(l), tt).tolist() for k, d, l in (('gA', A, 'gain'), ('gB', B, 'gain'), ('lA', A, 'low'), ('lB', B, 'low'), ('hA', A, 'high'), ('hB', B, 'high'))}
def build():
    import picker_1119 as P; HOLD = set(P.HOLD); acc = {16: [], 32: []}
    for v in VARS:
        p = os.path.join(H, 'gate_ckpt', v + '.jsonl')
        if not os.path.exists(p): continue
        for l in open(p):
            r = json.loads(l)
            if r.get('error') or r.get('dj') in HOLD or r.get('src') == 'protrans': continue
            try: X, L = lanes_from_meta(json.load(open(r['meta'])))
            except Exception: continue
            if X in acc: acc[X].append(L)
    out = {str(X): {k: np.median([L[k] for L in Ls], 0).round(4).tolist() for k in Ls[0]} | {'n': len(Ls)} for X, Ls in acc.items() if Ls}
    json.dump(out, open(TP, 'w'), indent=1); print({X: out[X]['n'] for X in out})
_T = None
def tmpl(X):
    global _T
    if _T is None: _T = json.load(open(TP))
    return _T.get(str(int(X)))
def vdip(L):
    L = np.asarray(L, float); best = 0.0
    for k in range(2, len(L) - 2): best = max(best, min(L[k-2:k].max(), L[k+1:k+3].max()) - L[k])
    return float(best)
def p10(x): return 10 ** (np.asarray(x, float) / 10)
def sim(Abar, Bbar, s, ib, X):
    """Abar/Bbar: st 'bar' dicts; s = first outgoing bar (e - X), ib = first incoming bar. -> dict of features (NaN if unavailable)"""
    T = tmpl(X); nan = dict(sim2_vdip=np.nan, sim2_lohi_vdip=np.nan, sim2_min_rel=np.nan)
    if T is None or not Abar or not Bbar or 'hat' not in Abar or 'hat' not in Bbar: return nan
    def seg(b, a): v = {k: np.asarray(b[k][max(0, a):a + X], float) for k in ('all', 'low', 'hat')}; return v if all(len(x) == X for x in v.values()) else None
    a, b = seg(Abar, s), seg(Bbar, ib)
    if a is None or b is None: return nan
    def deck(v, g, lo, hi):
        Pl, Ph = p10(v['low']), p10(v['hat']); Pm = np.maximum(p10(v['all']) - Pl - Ph, 0.05 * p10(v['all']))
        g, lo, hi = np.asarray(g), np.asarray(lo), np.asarray(hi); return g ** 2 * (lo ** 2 * Pl + Pm + hi ** 2 * Ph), g ** 2 * (lo ** 2 * Pl + hi ** 2 * Ph)
    fa, la = deck(a, T['gA'], T['lA'], T['hA']); fb, lb = deck(b, T['gB'], T['lB'], T['hB'])
    S = 10 * np.log10(fa + fb + 1e-12); LH = 10 * np.log10(la + lb + 1e-12)
    return dict(sim2_vdip=vdip(S), sim2_lohi_vdip=vdip(LH), sim2_min_rel=float(S.min() - S[0]))
def validate():
    """simulated vdip vs the rendered blend's measured pump_db on dev renders (Spearman), and the gap rule's hit rates"""
    import picker_1119 as P, safeplace_1119 as S
    from scipy.stats import spearmanr
    rows = {r['id']: r for r in S.dev_rows()}; xs, ys, fl = [], [], []
    for v in VARS:
        for k, arr in S.load(v).items():
            r = rows.get(k); w = arr.get('win')
            if r is None or not w or w[0] != 'n': continue
            e, ib, X = int(w[1]), int(w[3]), int(w[4]); A, B = S.st(r['ya']), S.st(r['yb'])
            f = sim(A, B, e - X, ib, X)
            if not np.isfinite(f['sim2_vdip']): continue
            xs.append(f['sim2_vdip']); ys.append(arr['hard_v1'].get('pump_db') or 0.0); fl.append(bool(arr['hard_v1'].get('pumping')))
    xs, ys, fl = map(np.array, (xs, ys, fl)); rho = spearmanr(xs, ys)[0]; gap = xs >= X_GAP
    res = dict(n=len(xs), spearman=round(float(rho), 3), X_GAP=X_GAP, gap_rate=round(float(gap.mean()), 3),
               pump_rate_if_gap=round(float(fl[gap].mean()), 3) if gap.any() else None, pump_rate_if_no_gap=round(float(fl[~gap].mean()), 3),
               pump_recall_of_gap=round(float(gap[fl].mean()), 3) if fl.any() else None)
    json.dump(res, open(os.path.join(H, 'lanesim_1119_validate.json'), 'w'), indent=1); print(res)
if __name__ == '__main__': {'build': build, 'validate': validate}[sys.argv[1]]()
