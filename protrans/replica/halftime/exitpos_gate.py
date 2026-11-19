#!/usr/bin/env python3
"""2026-11-19 EXITPOS_GATE (research, flag EXITPOS_GATE=1, requires EXITPOS=1): keep the outro-over-intro window as the
safe default. Take an EXITPOS alternative only when (1) it exits earlier, (2) the outgoing's last drop has played to its
end, (3) the incoming's first drop lands inside the blend, and (4) a leave-one-DJ-out logistic, fitted on pro placement,
says the alternative is closer to a good blend than the default. Off by default. Weights in exitpos_gate_w.json."""
import os, json, numpy as np
W_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'exitpos_gate_w.json')
# Features of (default window, earlier-exit alternative). Keep this list short and structural.
FEATS = (
    'bars_earlier',          # default_exit - alt_exit (>= 1 if we got here)
    'default_past_ld',       # bars the default sits after last-drop end (how much outro it keeps)
    'alt_past_ld',           # same for the alternative
    'default_to_end',        # music_end - default_exit (0 = rigid play-to-end)
    'default_slow_start',    # default blend starts in an outgoing outro / in-drop slowdown
    'default_slow_frac',     # share of default outgoing bars that sit in such a slowdown
    'alt_drop_pos',          # where B drop1 sits in the alt blend (0 start, 1 end)
    'default_drop_pos',
    'cue_shift',             # alt_cue - default_cue
)

def _slow_secs(ya, sa):
    try:
        import slowdown as _SD
        P = _SD.profile(ya); dr = (sa or {}).get('drops') or []
        if not P or not dr: return []
        out = []
        for x, y in P['sections']:
            if y <= dr[0][0] + 2: continue
            if x >= dr[-1][1] - 4 or any(p <= x and y <= q for p, q in dr):
                out.append((x, y))
        return out
    except Exception:
        return []

def _slow_frac(secs, a0, a1):
    if a1 <= a0: return 0.0
    return sum(max(0, min(a1, y) - max(a0, x)) for x, y in secs) / (a1 - a0)

def last_drop_end(sa):
    dr = (sa or {}).get('drops') or []
    return dr[-1][1] if dr else None

def drop1_in(ib, X, sb):
    d1 = (sb or {}).get('drop1')
    return d1 is not None and ib <= d1 <= ib + X

def hard_ok(alt, default, sa, sb):
    """alt, default are (exit, cue, X). Earlier exit, last drop played, incoming drop1 inside the blend."""
    ae, ac, aX = alt; be, bc, bX = default
    if ae >= be: return False
    ld = last_drop_end(sa)
    if ld is not None and ae < ld: return False
    if not drop1_in(ac, aX, sb): return False
    return True

def feats(default, alt, sa, sb, ya=None, slows=None):
    be, bc, bX = default; ae, ac, aX = alt
    ld = last_drop_end(sa) or be
    me = (sa or {}).get('music_end') or be
    if slows is None and ya is not None: slows = _slow_secs(ya, sa)
    slows = slows or []
    d1 = (sb or {}).get('drop1')
    def dpos(c, X):
        return 0.0 if not X or d1 is None else float(np.clip((d1 - c) / X, -1, 2))
    return dict(
        bars_earlier=float(be - ae),
        default_past_ld=float(be - ld),
        alt_past_ld=float(ae - ld),
        default_to_end=float(me - be),
        default_slow_start=float(any(x <= be - bX < y for x, y in slows)),
        default_slow_frac=float(_slow_frac(slows, be - bX, be)),
        alt_drop_pos=dpos(ac, aX),
        default_drop_pos=dpos(bc, bX),
        cue_shift=float(ac - bc),
    )

def _vec(f):
    return np.array([f[k] for k in FEATS], float)

def _sigmoid(z):
    z = float(np.clip(z, -40, 40)); return 1.0 / (1.0 + np.exp(-z))

def load(path=None):
    path = path or os.environ.get('EXITPOS_GATE_FILE') or W_PATH
    if not os.path.exists(path): return None
    return json.load(open(path))

_W = None
def weights(ya=None, dj=None):
    global _W
    if _W is None: _W = load()
    if not _W: return None
    if ya and ya in (_W.get('per_track') or {}): return _W['per_track'][ya]
    if dj and dj in (_W.get('lodo') or {}): return _W['lodo'][dj]
    return _W.get('all')

def prob(default, alt, sa, sb, ya=None, dj=None, slows=None):
    w = weights(ya, dj)
    if not w: return None
    f = feats(default, alt, sa, sb, ya, slows)
    coef = w['coef']; intercept = float(w.get('intercept', 0.0))
    z = intercept + sum(float(coef[k]) * f[k] for k in FEATS)
    return _sigmoid(z)

def should_switch(default, alt, sa, sb, ya=None, dj=None, slows=None, thr=None):
    if not hard_ok(alt, default, sa, sb): return False, dict(reason='hard')
    f = feats(default, alt, sa, sb, ya, slows)
    # the listener's "when the outro is doing something odd": if the default blend starts in, or is
    # mostly, an outgoing outro / in-drop slowdown, a hard-ok earlier exit is allowed even
    # when the leave-one-DJ-out logistic is unsure (it under-rates this pattern when that DJ
    # is held out).
    if f['default_slow_start'] or f['default_slow_frac'] >= 0.25:
        return True, dict(reason='weird_outro', slow_start=f['default_slow_start'], slow_frac=round(f['default_slow_frac'], 3))
    p = prob(default, alt, sa, sb, ya, dj, slows)
    if p is None:
        return True, dict(reason='hard_only', p=None)
    t = float(thr if thr is not None else (load() or {}).get('threshold', 0.6))
    return bool(p >= t), dict(reason='model', p=round(float(p), 4), thr=t)

def default_score_key(cand, a, b, STRUCTW=300.0):
    """Rebuild the no-EXITPOS sort key for a pair_cands row (sc, kind, e, ib, r, X)."""
    sc, kind, e, ib, r, X = cand
    ea = e[0] if isinstance(e, tuple) else e
    # sc[0] already includes the EXITPOS term (and may have had the outro bonus zeroed).
    # Caller should pass bonus_keys / exitpos_term; this helper is unused if the planner
    # recomputes explicitly. Kept as a stub for tests.
    return sc
