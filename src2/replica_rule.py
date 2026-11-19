"""REPLICA v1 (2026-11-18, off by default; flag REPLICA=1 / rules['REPLICA']).
Pro-replication window from track structure, per pair:
  - outgoing: blend starts where the outgoing's first drop ends (its breakdown), so the outgoing is
    cut before its second drop/outro, like pros do (protrans pros: 29/33 leave with >40 bars of music left;
    breakdown-start exit is within 16 bars of the pro on 36% of protrans pairs vs 6% for outro->intro).
  - incoming: drop1 - X, so the incoming drop lands at the blend end (in place of the outgoing's 2nd drop).
  - X: 32 when the outgoing breakdown is at least 32 bars long, else 16.
Window form: [kind, e, None, ib, X] (outgoing plays to e; incoming starts at ib)."""
import os

def flag_on(v=None):
    v = os.environ.get('REPLICA') if v is None else v
    return str(v).strip().lower() in ('1', 'true', 'yes', 'on')

def phrase(x, q=8):
    return int(round(float(x) / q) * q)

def fine_breakdown(a_id, after, root='.'):
    """v2 fallback: protrans/structure.py phase labels (finds short breakdowns that sections.py merges into one drop)."""
    import json, sys
    import numpy as np
    here = os.path.dirname(os.path.abspath(__file__)); p = os.path.join(here, '..', 'protrans')
    if p not in sys.path: sys.path.insert(0, p)
    import structure as ST
    g = json.load(open(os.path.join(root, 'st', f'{a_id}.json')))
    B = g['bar']; dr = np.asarray(B.get('drums') or B.get('all') or [], float); bs = np.asarray(B.get('bass') or B.get('low') or dr, float)
    n = min(len(dr), len(bs))
    spans = ST.phase_spans(ST.label_phases(dict(drums=dr[:n], bass=bs[:n], n=n)))
    for name, s0, e0 in spans:
        if name == 'breakdown' and s0 > after:
            nxt = next((s1 for nm, s1, _ in spans if nm == 'drop' and s1 > s0), None)
            return int(s0), int((nxt or e0) - s0)
    return None, None

def window(sa, sb, X=None, a_id=None):
    drops_a = [list(map(int, d)) for d in (sa.get('drops') or [])]
    na = int(sa.get('music_end') or sa.get('n_bars') or 0)
    nb = int(sb.get('music_end') or sb.get('n_bars') or 0)
    if len(drops_a) >= 2:
        bd = phrase(drops_a[0][1]); bd_len = drops_a[1][0] - drops_a[0][1]; src = 'sections'
    else:
        bd = bd_len = None
        if a_id and drops_a:
            try:
                b0, L = fine_breakdown(a_id, drops_a[0][0] + 16)
                if b0 is not None: bd, bd_len, src = phrase(b0), L, 'structure_fallback'
            except Exception:
                bd = None
        if bd is None:
            return None, 'outgoing has no detectable breakdown (no mid-track exit)'
    Xw = X or (32 if bd_len >= 32 else 16)
    d1 = int(sb.get('drop1') or 0)
    ib = phrase(max(0, d1 - Xw))
    e = bd + Xw
    if e > na or ib + Xw > nb or nb - ib < 48 or bd < 32:
        return None, 'window not legal'
    return ['n', e, None, ib, Xw], dict(bd=bd, bd_len=bd_len, drop1_b=d1, X=Xw, src=src)

def engine_cands(sa, sb, X, e_max=None, ia=0, a_id=None):
    w, _ = window(sa, sb, X=X, a_id=a_id)
    if not w:
        return []
    if e_max is not None and w[1] > e_max:
        return []
    if ia is not None and w[1] - X < int(ia):
        return []
    return [(w[0], w[1], w[3])]
