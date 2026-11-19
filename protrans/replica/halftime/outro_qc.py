#!/usr/bin/env python3
"""2026-11-19 OUTRO_QC (the listener's design call): keep the outro-over-intro bonus, but deduct when the outgoing's outro blend bars are "weird".
Features on the outgoing window [s, e) (bars of its stretched grid), each a yes/no:
  slow      the window touches a half-time / slowdown section (slowdown.py, any section type)
  drums_out median kick hits < 0.6 x the track's drop median (drums dropping out)
  snare_out median strong-snare hits < 0.35 x the track's drop mean
  energy    median full-band bar level > 6 dB under the drop median (big level / energy drop)
  fade      any bar of the window > 20 dB under the drop median (early fade toward silence)
  thin      median lows > 6 dB under the track's 75th-pct lows (THIN_DB line)
Deductions are fitted from pro data (fit_outro_qc_1119.py), not hand-set: for each feature, how much less often pros blend over the final
outro block when the feature is present (rate ratio with a +1 prior), as a fraction of the bonus."""
import os, sys, json
import numpy as np
H = os.path.dirname(os.path.abspath(__file__)); SRC2 = '/workspace/mixes/src2'; sys.path.insert(0, H)
FEATS = ('slow', 'drums_out', 'snare_out', 'energy', 'fade', 'thin')
W_PATH = os.path.join(H, 'outro_qc_w.json')

def feats(yt, s, e):
    import slowdown as SD
    g = json.load(open(os.path.join(SRC2, 'st', yt + '.json')))['bar']; sec = json.load(open(os.path.join(SRC2, 'st', yt + '.sections.json')))
    P = SD.profile(yt); dr = sec.get('drops') or []
    al = np.asarray(g['all'], float); lo = np.asarray(g.get('low', g['all']), float); n = len(al)
    w = [i for i in range(max(0, int(s)), min(int(e), n))]
    db = [i for x, y in dr for i in range(int(x), min(int(y), n))]
    if not w or not db: return None
    K = np.asarray(P['kicks'], float) if P else None; S = np.asarray(P['snare_strong'], float) if P else None
    wk = [i for i in w if K is not None and i < len(K)]; dk = [i for i in db if K is not None and i < len(K)]
    ref = float(np.median(al[db]))
    return dict(slow=bool(P and any(x < e and s < y for x, y in P['sections'])),
                drums_out=bool(wk and dk and np.median(K[wk]) < 0.6 * np.median(K[dk])),
                snare_out=bool(wk and dk and np.median(S[wk]) < 0.35 * max(np.mean(S[dk]), 1e-9)),
                energy=bool(np.median(al[w]) < ref - 6), fade=bool(np.min(al[w]) < ref - 20),
                thin=bool(np.median(lo[w]) - np.percentile(lo, 75) < -6))

_W = {}
def ded_from(w, f):
    """logit weights -> fraction of the bonus to remove: 1 - p(pro uses final block | f) / p(... | clean outro), clipped 0..1"""
    import math
    z0 = w['b']; z = z0 + sum(w['coef'].get(k, 0.0) for k in FEATS if f[k])
    p = 1 / (1 + math.exp(-z)); p0 = 1 / (1 + math.exp(-z0)); return float(min(1.0, max(0.0, 1 - p / p0)))

def deduction(yt, s, e, path=None):
    """fraction (0..1) of the outro-over-intro bonus to remove for this outgoing window; per-track leave-DJ-out weights when present"""
    path = path or os.environ.get('OUTRO_QC_FILE') or W_PATH
    if path not in _W: _W[path] = json.load(open(path))
    W = _W[path]; w = W.get('per_track', {}).get(yt) or W['all']
    f = feats(yt, s, e)
    if not f: return 0.0, None
    return ded_from(w, f), f
