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
    Xw = X or (int(os.environ['REPLICA_X']) if os.environ.get('REPLICA_X') else (32 if bd_len >= 32 else 16))  # REPLICA_X: research override (blend length)
    d1 = int(sb.get('drop1') or 0)
    ib = phrase(max(0, d1 - Xw))
    e = bd + Xw
    if e > na or ib + Xw > nb or nb - ib < 48 or bd < 32:
        return None, 'window not legal'
    return ['n', e, None, ib, Xw], dict(bd=bd, bd_len=bd_len, drop1_b=d1, X=Xw, src=src)

def engine_cands(sa, sb, X, e_max=None, ia=0, a_id=None):
    if mode() == 'gated':  # gated: only a confident (primary-detector) breakdown adds the replica window
        g, _ = gate(sa, sb, a_id=a_id)
        if not g: return []
        w, _ = window(dict(sa, drops=[list(map(int, d)) for d in sa.get('drops') or []]), sb, X=X)
    else:
        w, _ = window(sa, sb, X=X, a_id=a_id)
    if not w:
        return []
    if e_max is not None and w[1] > e_max:
        return []
    if ia is not None and w[1] - X < int(ia):
        return []
    return [(w[0], w[1], w[3])]

# ---------------------------------------------------------------------------------------------------------------------------
# REPLICA=gated (2026-11-18 night): per-pair option, not a blanket default (the listener's blind A/B: liked the replica on ukf__19,
# a clean two-drop outgoing; preferred the default on js08, where only the fine fallback found a breakdown).
# The replica window is used only when the PRIMARY sections detector (two separate drops) finds the breakdown, the breakdown is
# a clear low-band dip, and it is long enough to hold the blend. Otherwise the engine's default pick stands.
# Gate constants are a priori, not tuned on the eval: 6 dB is the same margin sections.py uses to call a bar a drop;
# 16 bars is the shortest blend the engine renders.
GATE_DIP_DB = 6.0
GATE_MIN_BD = 16

def mode(v=None):
    """'off' | 'on' (REPLICA=1, every pair) | 'gated' (REPLICA=gated, confident breakdowns only)"""
    v = os.environ.get('REPLICA') if v is None else v
    s = str(v).strip().lower() if v is not None else ''
    if s == 'gated': return 'gated'
    return 'on' if s in ('1', 'true', 'yes', 'on') else 'off'

def flag_on(v=None):  # noqa: F811 (gated also enables the candidate hook)
    return mode(v) != 'off'

def _bar_low(a_id, root='.'):
    import json
    import numpy as np
    g = json.load(open(os.path.join(root, 'st', f'{a_id}.json')))['bar']
    return np.asarray(g.get('low') or g.get('bass') or g['all'], float)

def gate(sa, sb, a_id=None, root='.', low=None):
    """(window or None, info). Window only when the breakdown is confident; info always says why."""
    import numpy as np
    drops = [list(map(int, d)) for d in (sa.get('drops') or [])]
    info = dict(path='default')
    if len(drops) < 2:
        info['why'] = 'primary detector found one drop (no confident breakdown)'; return None, info
    w, why = window(dict(sa, drops=drops), sb)
    if not w:
        info['why'] = why; return None, info
    bd0, bd1 = drops[0][1], drops[1][0]; info.update(bd=bd0, bd_len=bd1 - bd0)
    if bd1 - bd0 < GATE_MIN_BD:
        info['why'] = f'breakdown {bd1 - bd0} bars < {GATE_MIN_BD}'; return None, info
    try:
        lo = _bar_low(a_id, root) if low is None else np.asarray(low, float)
        d1 = float(np.median(lo[drops[0][0]:drops[0][1]])); bdm = float(np.median(lo[bd0:bd1]))
        info['dip_db'] = round(d1 - bdm, 1)
    except Exception as ex:
        info['why'] = f'no bar curve ({type(ex).__name__})'; return None, info
    if d1 - bdm < GATE_DIP_DB:
        info['why'] = f'breakdown dip {d1 - bdm:.1f} dB < {GATE_DIP_DB}'; return None, info
    info.update(path='replica', why='confident breakdown', win=w); return w, info

# ---------------------------------------------------------------------------------------------------------------------------
# DROPCAND (2026-11-18 late, off by default; research flag): drop-exit / drop-cue candidate windows.
# Relabel of dev misses: pros often leave the outgoing over the end of its drop 1 (exit-in-drop1 pros sit 45-65 bars into a
# drop), and on 20 dev pairs they cued the incoming at its own drop 1 (median +5 bars).
#   exit : blend = last X bars of the outgoing's drop 1 (e = drop1 end); incoming drop lands at the blend end (ib = drop1_b - X)
#   cue  : same outgoing span; incoming starts AT its drop 1 (ib = drop1_b): drop-on-drop for X bars
# DROPCAND=exit|cue forces that window when the engine scored it (like REPLICA=1); DROPCAND=both only adds both as candidates.
def drop_mode(v=None):
    v = os.environ.get('DROPCAND') if v is None else v
    s = str(v).strip().lower() if v is not None else ''
    if s in ('1', 'true', 'yes', 'on', 'both'): return 'both'
    return s if s in ('exit', 'cue') else 'off'

def drop_window(sa, sb, which, X=16):
    drops_a = [list(map(int, d)) for d in (sa.get('drops') or [])]
    if not drops_a: return None, 'outgoing has no drop'
    na = int(sa.get('music_end') or sa.get('n_bars') or 0); nb = int(sb.get('music_end') or sb.get('n_bars') or 0)
    d1b = int(sb.get('drop1') or 0)
    if d1b <= 0: return None, 'incoming has no drop1'
    e = phrase(drops_a[0][1]); X = int(X)
    ib = phrase(d1b) if which == 'cue' else phrase(max(0, d1b - X))
    if e > na or e - X < 32 or ib + X > nb or nb - ib < 48:
        return None, 'window not legal'
    return ['n', e, None, ib, X], dict(which=which, drop1_a=drops_a[0], drop1_b=d1b, X=X)

def drop_engine_cands(sa, sb, X, e_max=None, ia=0):
    m = drop_mode(); out = []
    for which in (('exit', 'cue') if m == 'both' else (m,)):
        w, _ = drop_window(sa, sb, which, X=X)
        if not w: continue
        if e_max is not None and w[1] > e_max: continue
        if ia is not None and w[1] - X < int(ia): continue
        out.append((w[0], w[1], w[3]))
    return out
