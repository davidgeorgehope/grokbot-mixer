"""STRUCT_BREAK (2026-11-23 RCA, research, off by default).

On a two-drop outgoing track whose first drop is followed by a breakdown (a gap
before drop 2), move the STRUCT outro-over-intro bonus to already-scored
phrase-complete exits at drop-1 end or breakdown end / drop-2 start, and cue
the incoming so the next intro energy event lands inside the blend with a
lead-in.

The arrival event is the first incoming half-time / slowdown that starts after
bar 16 and before drop 1 (so a very-early intro half-time is skipped); if none,
drop 1 itself. Lead-in is 16 bars on a 32-bar blend and 8 bars on a 16-bar
blend; the event must also not sit in the last 4 bars of the window.

Structure only: sections.json + slowdown.py. No pro audio, no per-track pins.
If no legal phrase window exists, the default outro-over-intro bonus is left
alone.

This module does not write rules.json or change defaults.
"""
from __future__ import annotations
import os, sys

STRUCTW = float(os.environ.get('STRUCTW', 300))
LOG = []


def flag_on(val=None):
    v = os.environ.get('STRUCT_BREAK') if val is None else val
    return str(v or '0') not in ('', '0', 'false', 'False')


def arrival_event(b, sections, slowdown_profile=None):
    SB = sections.get(b) or {}
    d1 = SB.get('drop1')
    ev = d1
    try:
        P = slowdown_profile
        if P is None:
            sys.path.insert(0, '/workspace/mixes/protrans/replica/halftime')
            import slowdown as _SD
            P = _SD.profile(b)
        for x, y in (P or {}).get('sections') or []:
            if d1 is not None and 16 < x < d1:
                ev = x
                break
    except Exception as ex:
        print('STRUCT_BREAK event failed', b, ex, file=sys.stderr)
    return ev


def eligible_exits(SA, e_max, emin, ia, X):
    """Grid-aligned exits at drop-1 end and at the start of drop 2 (breakdown end)."""
    dr = SA.get('drops') or []
    if len(dr) < 2:
        return []
    d1e = int(dr[0][1])
    d2s = int(dr[1][0])
    if not (d1e < d2s):
        return []
    outs = []
    for raw in (d1e, d2s):
        e = int(round(raw / 16.0)) * 16
        if emin <= e <= e_max and e - X >= ia + 16:
            outs.append(e)
    return sorted(set(outs))


def collect(a, b, X, cands, e_max, emin, ia, sections):
    """Return (suppress_outro_bonus, bonus_keys).

    bonus_keys are ('n', a, b, e, ib, X) windows that should inherit STRUCTW.
    """
    SA, SB = sections.get(a) or {}, sections.get(b) or {}
    exits = eligible_exits(SA, e_max, emin, ia, X)
    ev = arrival_event(b, sections)
    keys = set()
    if not exits or ev is None:
        LOG.append(dict(a=a, b=b, X=X, ev=ev, exits=exits, keys=[], active=False))
        return False, keys
    lead = 16 if X >= 32 else 8
    for kind, e, ib in cands:
        if kind != 'n':
            continue
        ee = e[0] if isinstance(e, tuple) else e
        if ee not in exits:
            continue
        if ib + lead <= ev <= ib + X - 4:
            keys.add(('n', a, b, ee, ib, X))
    active = bool(keys)
    LOG.append(dict(a=a, b=b, X=X, ev=ev, lead=lead, exits=exits,
                    keys=[list(k) for k in sorted(keys, key=lambda t: (t[5], t[3], t[4]))],
                    active=active))
    print('STRUCT_BREAK', a, b, 'X', X, 'ev', ev, 'exits', exits, 'keys', sorted(keys),
          'suppress_outro', active, file=sys.stderr)
    return active, keys
