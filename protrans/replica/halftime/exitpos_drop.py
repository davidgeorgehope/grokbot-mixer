#!/usr/bin/env python3
"""2026-11-19 EXITPOS_DROP (research, flag EXITPOS_DROP=1, requires EXITPOS=1, off by default).

A second arm next to EXITPOS_GATE (strict). Allows an exit right at the end of the last
drop (the epg2 behaviour: the blend covers the last bars of a still-hot drop) only when:

1. The incoming's first drop lands inside the blend.
2. The outgoing outro is quieter or thinner than the last 16 bars of the last drop.
3. Pro placement, when known, does not show the outro carrying the blend
   (majority of the pro outgoing overlap sits at or after last-drop end), as with
   hybrid_minds_ukf__45.
4. The window does not hard-fail, when a hard-check result is already on disk.
   Unknown windows are allowed here and vetoed after render in the eval.

the listener's ear ([pt556u] on netsky_hospital_classics__02, and earlier joe_syntax_hospital__01)
prefers this pattern even when pro-match is lower. A pro-match drop alone does not kill the arm.
Does not change EXITPOS_GATE / epg_strict.
"""
import os, json, numpy as np

QUIET_DB = 3.0
THIN_DB = 3.0
PRO_OUTRO_FRAC = 0.5
HF_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'exitpos_drop_hf.json')
PRO_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'exitpos_drop_pro.json')

def last_drop_end(sa):
    dr = (sa or {}).get('drops') or []
    return dr[-1][1] if dr else None

def drop1_in(ib, X, sb):
    d1 = (sb or {}).get('drop1')
    return d1 is not None and ib <= d1 <= ib + X

def hard_ok_drop(alt, default, sa, sb):
    """Earlier exit, last drop finished by the exit, blend still covers the end of that drop,
    incoming drop 1 inside the blend. This is the epg2 last-drop-end window, not the strict
    'last drop fully played before the blend starts' rule."""
    ae, ac, aX = alt; be, bc, bX = default
    if ae >= be: return False
    ld = last_drop_end(sa)
    if ld is None: return False
    if ae < ld: return False
    if ae - aX >= ld: return False
    if not drop1_in(ac, aX, sb): return False
    return True

def _bar_med(st, key, lo, hi):
    arr = np.array(st['bar'].get(key) or [], float)
    i0, i1 = max(0, int(round(lo))), max(0, int(round(hi)))
    if i1 <= i0 or i0 >= len(arr): return None
    return float(np.median(arr[i0:min(i1, len(arr))]))

def outro_quiet_or_thin(ya, sa, st=None):
    """True when the first 16 bars of the outgoing outro (or whatever remains) are at least
    QUIET_DB quieter on all-bands, or THIN_DB thinner on lows, than the last 16 of the last drop."""
    ld = last_drop_end(sa)
    me = (sa or {}).get('music_end')
    if ld is None or me is None or me <= ld: return False, dict(reason='no_outro')
    if st is None:
        p = os.path.join(os.environ.get('SRC2_ST', 'st'), f'{ya}.json')
        if not os.path.exists(p):
            p = f'/workspace/mixes/src2/st/{ya}.json'
        if not os.path.exists(p): return False, dict(reason='no_st')
        st = json.load(open(p))
    drop_all = _bar_med(st, 'all', ld - 16, ld)
    drop_low = _bar_med(st, 'low', ld - 16, ld)
    out_hi = min(me, ld + 16)
    out_all = _bar_med(st, 'all', ld, out_hi)
    out_low = _bar_med(st, 'low', ld, out_hi)
    if None in (drop_all, drop_low, out_all, out_low):
        return False, dict(reason='no_energy')
    d_all = drop_all - out_all
    d_low = drop_low - out_low
    ok = bool(d_all >= QUIET_DB or d_low >= THIN_DB)
    return ok, dict(reason='energy', d_all=round(d_all, 2), d_low=round(d_low, 2),
                    quiet=bool(d_all >= QUIET_DB), thin=bool(d_low >= THIN_DB))

_PRO = None
def load_pro():
    """Map (ya, yb) -> (out_bar_at_entry, out_bar_at_gone). Built once from the 33-pair
    decisions plus corpus-v2 features when present. Missing pairs simply have no veto."""
    global _PRO
    if _PRO is not None: return _PRO
    out = {}
    path = os.environ.get('EXITPOS_DROP_PRO') or PRO_CACHE
    if os.path.exists(path):
        raw = json.load(open(path))
        for k, v in raw.items():
            a, b = k.split('>', 1) if '>' in k else (None, None)
            if a: out[(a, b)] = (float(v[0]), float(v[1]))
        _PRO = out; return _PRO
    # live build (eval scripts may have already written the cache)
    _PRO = out; return _PRO

def pro_outro_carried(ya, yb, sa, pro=None):
    """True when the pro outgoing blend is mostly in the outro (frac >= PRO_OUTRO_FRAC
    of [entry, gone] sits at or after last-drop end). No pro data -> no veto."""
    ld = last_drop_end(sa)
    if ld is None: return False, dict(reason='no_ld', frac=None)
    if pro is None:
        pro = load_pro().get((ya, yb))
    if not pro: return False, dict(reason='no_pro', frac=None)
    a0, a1 = float(pro[0]), float(pro[1])
    if a1 <= a0: return False, dict(reason='bad_pro', frac=None)
    overlap = max(0.0, min(a1, 1e9) - max(a0, ld))
    frac = overlap / (a1 - a0)
    hit = bool(frac >= PRO_OUTRO_FRAC)
    return hit, dict(reason='pro_outro', frac=round(frac, 3), pro=[round(a0, 2), round(a1, 2)], ld=ld)

_HF = None
def load_hf():
    global _HF
    if _HF is not None: return _HF
    path = os.environ.get('EXITPOS_DROP_HF') or HF_CACHE
    if os.path.exists(path):
        raw = json.load(open(path))
        _HF = {(t[0], t[1], int(t[2]), int(t[3]), int(t[4])): bool(t[5]) for t in raw}
    else:
        _HF = {}
    return _HF

def known_hard_fail(ya, yb, alt):
    ae, ac, aX = alt
    v = load_hf().get((ya, yb, int(ae), int(ac), int(aX)))
    return v  # True / False / None if unknown

def should_switch_drop(default, alt, sa, sb, ya=None, yb=None, pro=None, st=None):
    if not hard_ok_drop(alt, default, sa, sb):
        return False, dict(reason='hard')
    ok_e, einfo = outro_quiet_or_thin(ya, sa, st=st)
    e = {k: v for k, v in einfo.items() if k != 'reason'}
    if not ok_e:
        return False, dict(reason=einfo.get('reason', 'energy'), **e)
    carried, pinfo = pro_outro_carried(ya, yb, sa, pro=pro)
    p = {k: v for k, v in pinfo.items() if k != 'reason'}
    if carried:
        return False, dict(reason='pro_outro', **p)
    hf = known_hard_fail(ya, yb, alt) if ya and yb else None
    if hf is True:
        return False, dict(reason='hard_fail', **e, **p)
    info = dict(reason='drop_end', **e)
    if p.get('frac') is not None: info['pro_frac'] = p['frac']
    if hf is False: info['known_hard_fail'] = False
    return True, info
