"""LEVEL_COMP (2026-11-27 midnight research, OFF by default): incoming-fader pull-forward through a predicted summed-level V-dip.
Idea: close the loop on the *summed* level of the two decks, not only on window choice (ESTAB) or fader shape.
  - Perez-Gonzalez & Reiss, "Automatic Gain and Fader Control For Live Mixing", WASPAA 2009 (cross-adaptive gain from loudness of the mix bus);
  - Manabe, "On the Measurability of DJ Mix Quality" (2026), loudness-control term dL = L_C - max(L_A, L_B);
  - MixWeaver (ISMIR 2026) 'total energy stability' objective; DJustify (arXiv 2610.33434) re-cue repair of energy holes.
Per blend: predict the per-bar summed level from both decks' stored per-bar levels x their gain lanes; where the worst
V-shaped dip (same definition as replica/hardcheck.vdip: bar below both the 2 bars before and the 2 after) exceeds TRIG dB,
raise the INCOMING deck's gain just enough to refill it (never above unity gain, never above +CAP dB over plan), then hold
that level until the planned curve overtakes it, so the incoming lane stays monotone and the outgoing lane is untouched.
No test, threshold or rules.json is changed; with LEVEL_COMP unset the engine is untouched."""
import os, numpy as np

def on():
    return os.environ.get('LEVEL_COMP', '0') not in ('', '0')

def _lane(pts, b):
    if not pts: return 1.0
    return float(np.interp(b, [p[0] for p in pts], [p[1] for p in pts]))

def _deck_db(d, lv, b):
    k = int(np.floor(b - d['start_bar']))
    fm = d.get('full_map') or []
    if not (0 <= k < len(fm)): return None
    sb = fm[k][0] if isinstance(fm[k], (list, tuple)) else fm[k]
    sb = min(max(int(sb), 0), len(lv) - 1)
    return float(lv[sb])

def _vdip(L):
    best, at = 0.0, None
    for k in range(2, len(L) - 2):
        v = min(max(L[k-2:k]), max(L[k+1:k+3])) - L[k]
        if v > best: best, at = v, k
    return best, at

def apply(decks, trans, lv_of, skip=(), trig=None, cap=None):
    trig = float(os.environ.get('LEVEL_COMP_TRIG', 2.5)) if trig is None else trig
    cap = float(os.environ.get('LEVEL_COMP_CAP', 9.0)) if cap is None else cap
    log = []
    for i, t in enumerate(trans):
        if t['a'] in skip or i + 1 >= len(decks): continue
        dA, dB = decks[i], decks[i + 1]
        s, e = int(np.floor(float(t['start_bar']))), int(np.ceil(float(t['end_bar'])))
        if e - s < 6: continue
        try:
            la, lb = lv_of(dA['id']), lv_of(dB['id'])
        except Exception:
            continue
        gA, gB = dA['auto'].get('gain') or [], dB['auto'].get('gain') or []
        bars = list(range(s, e))
        pa, pb, ga, gb = [], [], [], []
        for b in bars:
            m = b + 0.5
            xa, xb = _deck_db(dA, la, m), _deck_db(dB, lb, m)
            on_a = xa is not None; on_b = xb is not None
            pa.append(10 ** (xa / 10) if on_a else 0.0); pb.append(10 ** (xb / 10) if on_b else 0.0)
            ga.append(_lane(gA, m) ** 2); gb.append(_lane(gB, m) ** 2)
        pa, pb, ga, gb = map(np.array, (pa, pb, ga, gb))
        gb0 = gb.copy(); boost = np.ones(len(bars))
        L = lambda: 10 * np.log10(ga * pa + gb * pb + 1e-12)
        d0, _ = _vdip(L()); worst0 = d0
        for _ in range(8):
            Lc = L(); dp, k = _vdip(Lc)
            if k is None or dp <= trig: break
            tgt = Lc[k] + min(dp, cap) * 1.0
            need = 10 ** (tgt / 10) - ga[k] * pa[k]
            if pb[k] <= 0 or need <= 0: break
            g2 = min(need / pb[k], 1.0)
            if g2 <= gb[k] * 1.01: break
            gb[k] = g2
            # pull forward monotone: later bars (until planned curve overtakes) hold at least this level
            for j in range(k + 1, len(bars)): gb[j] = max(gb[j], g2)
        if np.allclose(gb, gb0): continue
        d1, _ = _vdip(L())
        # write the incoming lane over [s, e]: planned lane, raised to the repaired per-bar level at bar centres (linear in gain between)
        grid = np.arange(s, e + 1e-9, 0.25)
        base = np.array([_lane(gB, x) for x in grid])
        rep_x = [s] + [b + 0.5 for b in bars] + [e]
        rep_y = [gb0[0] ** .5 if gb[0] == gb0[0] else gb[0] ** .5] + [g ** .5 for g in gb] + [gb[-1] ** .5]
        rep = np.interp(grid, rep_x, rep_y)
        new = np.maximum(base, np.where(rep > base * 1.0001, rep, 0))
        new = np.maximum.accumulate(new) if np.all(np.diff(base) >= -1e-9) else new
        keep = [p for p in gB if p[0] < s or p[0] > e]
        lane = sorted(keep + [[round(float(x), 5), round(float(y), 5)] for x, y in zip(grid, new)])
        dB['auto']['gain'] = lane
        t['level_comp'] = dict(pred_vdip_before=round(float(worst0), 2), pred_vdip_after=round(float(d1), 2))
        t['tech'] = t.get('tech', '') + ' + level-comp'
        log.append(dict(a=t['a'], b=t['b'], before=round(float(worst0), 2), after=round(float(d1), 2)))
    return log
