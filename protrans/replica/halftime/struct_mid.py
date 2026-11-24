#!/usr/bin/env python3
"""STRUCT_MID (2026-11-23 research, off by default).

When the outgoing track has a post-drop breakdown or half-time section that can
host a mid-track exit (S.P.Y bars 128-160 is the prototype), mix_simple reduces
the outro-over-intro bonus and gives a competing bonus to exits at the end of
drop 1 or at the end of that breakdown.

Pick-time inputs are outgoing-track sections and slowdown.py sections only.
Pro exit/cue labels are never read here (they are training / evaluation targets
only).

The first gate (gap >= 16 or 8 bars of half-time in the gap) was too loose on
the 2026-11-23 fresh mixes: it fired on 18/19 transitions, mid-track pros are
only 5/19, and exit error rose 30.7 -> 55.58 (errors; lower is better). A
leave-one-mix-out sweep of (min gap, min half-time bars) on 52 labelled
transitions (33 protrans + 19 fresh, 9 mixes) chose min gap 16 and min
half-time 24 on 8 of 9 held-out mixes. Those are the defaults for
STRUCT_MID_MIN_GAP and STRUCT_MID_MIN_HT. S.P.Y (gap 32, 31 bars of
half-time in the gap) still fires.
"""
import os, sys

HT = os.path.dirname(os.path.abspath(__file__))
SRC2 = '/workspace/mixes/src2'
for p in (HT, SRC2):
    if p not in sys.path:
        sys.path.insert(0, p)

_CACHE = {}

def _overlap(secs, a, b):
    if not secs or b <= a:
        return 0
    return sum(max(0, min(b, y) - max(a, x)) for x, y in secs)

def _snap16(x):
    if x is None:
        return None
    s = int(x) - (int(x) % 16)
    return s if s > 0 else None

def mins():
    """Return (min_gap, min_halftime_bars) for the tight gate. Overridable."""
    return int(float(os.environ.get('STRUCT_MID_MIN_GAP', 16))), int(float(os.environ.get('STRUCT_MID_MIN_HT', 24)))

def should_fire(gap_len, sd_in_gap, min_gap=None, min_ht=None):
    """Tight gate: post-drop gap at least min_gap bars AND at least min_ht
    bars of slowdown/half-time inside that gap. Defaults 16 and 24."""
    if min_gap is None or min_ht is None:
        dg, dh = mins()
        if min_gap is None: min_gap = dg
        if min_ht is None: min_ht = dh
    return int(gap_len or 0) >= int(min_gap) and int(sd_in_gap or 0) >= int(min_ht)

def pocket(yt, sec=None):
    """Return the mid-track exit pocket on outgoing track `yt`, or None.

    Fires when the post-drop-1 gap before the next drop (or the outro, if
    there is only one drop) is at least STRUCT_MID_MIN_GAP (16) bars and
    contains at least STRUCT_MID_MIN_HT (24) bars of slowdown.py half-time
    / no-snare. The gap length floor is implied by the half-time floor
    whenever min_ht > min_gap.
    """
    key = (yt,) + mins()
    if key in _CACHE:
        return _CACHE[key]
    _cwd = os.getcwd()
    if not os.path.exists(os.path.join(_cwd, 'st', str(yt) + '.json')):
        os.chdir(SRC2)
    try:
        return _pocket(yt, sec)
    finally:
        os.chdir(_cwd)

def _pocket(yt, sec=None):
    import sections, slowdown as SD
    sa = sec if sec is not None else sections.get(yt)
    info = dict(yt=yt, fire=False, why='no_sections', gap=None, gap_len=0,
                sd_in_gap=0, anchors=[], drops=None)
    if not sa:
        _CACHE[(yt,)+mins()] = None
        return None
    drops = list(sa.get('drops') or [])
    outro = sa.get('outro_start')
    info['drops'] = drops
    gap = None
    if len(drops) >= 2:
        gap = (drops[0][1], drops[1][0])
    elif len(drops) == 1 and outro and outro > drops[0][1]:
        gap = (drops[0][1], outro)
    info['gap'] = gap
    info['gap_len'] = 0 if not gap else max(0, gap[1] - gap[0])
    sd = []
    try:
        P = SD.profile(yt)
        sd = list((P or {}).get('sections') or [])
    except Exception as ex:
        info['sd_err'] = f'{type(ex).__name__}: {ex}'
    info['sd_sections'] = sd
    info['sd_in_gap'] = _overlap(sd, gap[0], gap[1]) if gap else 0
    info['min_gap'], info['min_ht'] = mins()
    if not should_fire(info['gap_len'], info['sd_in_gap'], info['min_gap'], info['min_ht']):
        info['why'] = f"gate_fail gap={info['gap_len']} sd_in_gap={info['sd_in_gap']} need gap>={info['min_gap']} and ht>={info['min_ht']}"
        _CACHE[(yt,)+mins()] = None
        return None
    anchors = []
    if drops:
        a1 = _snap16(drops[0][1])
        if a1:
            anchors.append(a1)
    if gap:
        a2 = _snap16(gap[1])
        if a2 and a2 not in anchors:
            anchors.append(a2)
    if not anchors:
        info['why'] = 'no_grid_anchor'
        _CACHE[(yt,)+mins()] = None
        return None
    info['fire'] = True
    info['why'] = f"tight_gate gap={info['gap_len']} sd_in_gap={info['sd_in_gap']}"
    info['anchors'] = anchors
    _CACHE[(yt,)+mins()] = info
    return info

def mid_exit(yt, e, tol=8, sec=None):
    p = pocket(yt, sec=sec)
    if not p:
        return False
    return any(abs(int(e) - a) <= tol for a in p['anchors'])

if __name__ == '__main__':
    for yt in sys.argv[1:]:
        print(yt, pocket(yt))
