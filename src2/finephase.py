"""Per-phrase beat-phase correction (2026-11-17 RCA: Cyantific 'Ghetto Blaster' intro sat 151 ms
early vs the track's drop-locked grid, so a 16-bar intro cue flammed against Logistics
'We Are One (Nu:Logic Remix)' by ~80-130 ms).

prep.grid() / halfbeat.fix_grid() fit one phase for the whole track and only test a half-beat
shift. A section whose kick/snare template sits a quarter to a third of a beat off that global
grid (Ghetto Blaster's intro: phase -0.438 beat, strength 5.5) is never moved, and
engine._bars places every bar at d0 + bar * BAR with no local correction.

This module measures the same kick-on-1 / snare-on-2-and-4 template (halfbeat.deck_phase)
on each 8-bar phrase. When the fit is confident and the local phase is at least MIN_MS off
the grid, those source bars get a constant time nudge (ms). engine.nudge() adds it when
FINE_PHASE is on. Existing nudge.json entries still apply on top.

The nudge sign matches engine._bars (positive = read the source earlier so early hits land
later on the mix grid) and autofix.py: nudge_ms = -phase_beats * beat_period_ms.

Off by default (FINE_PHASE=0). Not a loosened guardrail: X1, GAP_DB, HALFBEAT_* and F1/N1
thresholds are unchanged. A weak or short phrase is left alone.
"""
from __future__ import annotations
import json, os
import numpy as np
import halfbeat as HB

# 8-bar phrases; 20 ms is just under one 64-bin step (BAR/64 = 21.6 ms). Strength is the
# template's margin vs the half-beat-away fit (same z-units as HALFBEAT_MARGIN).
MIN_MS = float(os.environ.get('FINE_PHASE_MIN_MS', 20))
MIN_STRENGTH = float(os.environ.get('FINE_PHASE_MIN_STRENGTH', 1.5))
MIN_BARS = int(os.environ.get('FINE_PHASE_MIN_BARS', 8))
PHRASE = 8
BEAT_MS = HB.BEAT * 1000

_CACHE = {}


def flag_on(val=None):
    v = os.environ.get('FINE_PHASE', '0') if val is None else val
    if v is None:
        return False
    s = str(v).strip().lower()
    return s not in ('', '0', 'false', 'off', 'no')


def clear():
    _CACHE.clear()


def _phrases(n):
    """Non-overlapping 8-bar windows from bar 0; a leftover tail of MIN_BARS or more is included."""
    out = []
    i = 0
    while i + MIN_BARS <= n:
        j = min(i + PHRASE, n)
        if j - i < MIN_BARS:
            break
        out.append(list(range(i, j)))
        i += PHRASE
    return out


def phrase_nudges(tid, g=None):
    """{bar_index: nudge_ms} for track tid (st/<tid>.json + .wav). 0-nudge phrases omitted."""
    if tid in _CACHE:
        return _CACHE[tid]
    path = f'st/{tid}.json'
    if not os.path.exists(path) or not os.path.exists(f'st/{tid}.wav'):
        _CACHE[tid] = {}
        return _CACHE[tid]
    g = g or json.load(open(path))
    n = len(g['downs'])
    nudges = {}
    report = []
    for bars in _phrases(n):
        try:
            ph, strength, used = HB.deck_phase(tid, bars, g)
        except Exception:
            continue
        if used < MIN_BARS or strength < MIN_STRENGTH:
            continue
        ms = -ph * BEAT_MS
        if abs(ms) < MIN_MS:
            continue
        ms = float(round(ms, 1))
        for k in bars:
            nudges[k] = ms
        report.append(dict(bars=[bars[0], bars[-1]], phase=round(float(ph), 3),
                           nudge_ms=ms, strength=round(float(strength), 3), n=int(used)))
    _CACHE[tid] = nudges
    _CACHE[(tid, 'report')] = report
    return nudges


def report(tid, g=None):
    phrase_nudges(tid, g)
    return _CACHE.get((tid, 'report'), [])


def nudge_ms(tid, bar):
    """Nudge in ms for source bar `bar` of track tid; 0 if none / uncomputable."""
    return float(phrase_nudges(tid).get(int(bar), 0.0))


# ---- blend-time incoming lock (the 2026-11-17 fix) ----
# Phrase-to-grid nudges (FINE_PHASE) left ~37 ms on this pair and moved the outgoing track,
# which dropped the pro-similarity score 58.04 -> 38.46. A DJ beatmatches the incoming record
# to the one already playing. BLEND_LOCK measures the signed kick+snare lag (A minus B, ms)
# on bars where both decks are loud and delays or advances only the incoming deck by that lag.
# On We Are One -> Ghetto Blaster the loud-bar lag is +123 ms; a +120 ms incoming nudge
# leaves ~1.5 ms on the clash bars and a 9.7 ms pro-lock (under the 15 ms F1 line).
LOCK_MIN_MS = float(os.environ.get('BLEND_LOCK_MIN_MS', 15))   # already locked (F1 threshold)
LOCK_MAX_MS = float(os.environ.get('BLEND_LOCK_MAX_MS', 150))  # leave half-beat cases to halfbeat.py (~172 ms)


def lock_flag_on(val=None):
    v = os.environ.get('BLEND_LOCK', '0') if val is None else val
    if v is None:
        return False
    s = str(v).strip().lower()
    return s not in ('', '0', 'false', 'off', 'no')


def longest_run(idxs):
    """Longest consecutive run of bar indices. Isolated fade bars (e.g. 232 after a gap at 231) are dropped."""
    xs = sorted(int(i) for i in idxs)
    if not xs:
        return []
    best, cur = [xs[0]], [xs[0]]
    for a, b in zip(xs, xs[1:]):
        if b == a + 1:
            cur.append(b)
        else:
            if len(cur) > len(best):
                best = cur
            cur = [b]
    if len(cur) > len(best):
        best = cur
    return best


# A 20 ms radius holds the +123 ms clash bars (span ~8 ms) and a tight real lag
# like -67 ms over 8 bars, but will not glue a 0-to-40 ms smear or two far-apart
# misfires into a false lock. Three agreeing bars, and a majority of the loud run,
# are required before we move a deck (2026-11-17 eval: a 2-bar / 50 ms rule
# applied -61 ms to already-locked pairs and dropped held-out scores 4-7 points).
CLUSTER_RAD = 20.0
MIN_CLUSTER = 3
MAX_CLUSTER_SPAN = 25.0  # a 23-to-57 ms smear is not a lock (joe_syntax__01)


def robust_lag(vals, beat_ms=None, prefer_zero=False, radius=None, min_n=2):
    """Median of the largest cluster of lag values (ms).

    After a lock is already on the incoming deck, 2-bar xcorr often hops to a
    half-beat edge peak even though the true residual (and a strong secondary
    peak) is near 0. prefer_zero then takes the nearest-to-zero cluster that has
    at least one member inside 40 ms, falling back to the largest cluster if
    none is close."""
    v = [float(x) for x in vals if x is not None and np.isfinite(x)]
    if len(v) < min_n:
        return None
    rad = CLUSTER_RAD if radius is None else float(radius)
    clusters = []
    seen = set()
    for c in v:
        cl = tuple(x for x in v if abs(x - c) <= rad)
        if cl in seen:
            continue
        seen.add(cl)
        clusters.append(cl)
    def key(cl, zero=False):
        med = float(np.median(cl))
        std = float(np.std(cl) if len(cl) > 1 else 0)
        if zero:
            return (-abs(med), len(cl), -std)
        return (len(cl), -std, -abs(med))
    if prefer_zero:
        near = [cl for cl in clusters if abs(float(np.median(cl))) <= 40]
        if near:
            cl = max(near, key=lambda c: key(c, zero=True))
            return float(np.median(cl))
    cl = max(clusters, key=lambda c: key(c, zero=False))
    return float(np.median(cl))


def confident_lag(vals, beat_ms=None):
    """Lag to apply: tight cluster of at least MIN_CLUSTER bars, and a majority of the finite values.
    Returns None if the offsets are too messy to justify moving a deck."""
    v = [float(x) for x in vals if x is not None and np.isfinite(x)]
    if len(v) < MIN_CLUSTER:
        return None
    lag = robust_lag(v, beat_ms, prefer_zero=False, radius=CLUSTER_RAD, min_n=MIN_CLUSTER)
    if lag is None:
        return None
    cl = [x for x in v if abs(x - lag) <= CLUSTER_RAD]
    if len(cl) < MIN_CLUSTER or len(cl) < 0.5 * len(v):
        return None
    if (max(cl) - min(cl)) > MAX_CLUSTER_SPAN:
        return None
    # Do not apply a 17 ms "lock" that swallowed an already-locked 10 ms bar
    # (hybrid_minds_ukf__19: 1-bar offs [29, 17.4, 10.2, 158], pro-lock was 4.4 ms).
    if any(abs(x) < LOCK_MIN_MS for x in cl):
        return None
    return float(np.median(cl))


def reliable_offsets(A, B, bars, bs, beat):
    """Per-bar lag for plots: 1-bar window, falling back to a 2-bar interior peak
    when the 1-bar argmax has hopped to a wrap but a near-zero 2-bar peak is strong.
    After the +123.4 ms lock, bar 230 is -1.3 ms on 1 bar and a wrap on 2 bars
    (the window includes the fade); bar 229 is the other way around."""
    import blend_diag as D
    import numpy as np
    o1 = D.bar_offsets(A, B, list(bars), bs, beat, win_bars=1, prefer_interior=True)
    o2 = D.bar_offsets(A, B, list(bars), bs, beat, win_bars=2, prefer_interior=True)
    out = []
    for a, b in zip(o1, o2):
        near = [x for x in (a, b) if np.isfinite(x) and abs(float(x)) <= 15]
        if near:
            out.append(float(near[0]))
        else:
            out.append(float(a) if np.isfinite(a) else (float(b) if np.isfinite(b) else np.nan))
    return np.array(out)


def loud_lag_ms(A, B, bars, bs, beat, loud, prefer_zero=False):
    """Robust A-minus-B lag (ms, + = A late) on `loud` bar indices; None if not confident.

    Uses 1-bar windows so a fading next bar cannot flip the peak (bar 230 of the
    2026-11-17 pair is +122 ms on 1 bar and a false -51 ms on a 2-bar window).
    After a lock, also prefer an interior / near-zero xcorr peak when the 1-bar
    or 2-bar argmax has hopped to a half-beat wrap."""
    import blend_diag as D
    if len(loud) < 2:
        return None, []
    offs = D.bar_offsets(A, B, list(loud), bs, beat, win_bars=1,
                         prefer_interior=bool(prefer_zero))
    shown = [None if not np.isfinite(x) else round(float(x), 1) for x in offs]
    if prefer_zero:
        lag = robust_lag(offs, beat * 1000, prefer_zero=True)
    else:
        lag = confident_lag(offs, beat * 1000)
    return lag, shown


def measure_blend_lag(decks, trans, i):
    """Render blend i's decks as they stand and return (lag_ms, report) or (None, report)."""
    import blend_diag as D
    import engine as E
    M = dict(decks=decks, trans=trans)
    s0, yA, yB = D.crop_decks(M, i)
    t = trans[i]
    s, e = float(t['start_bar']), float(t['end_bar'])
    nbars = int(round(len(yA) / E.BS))
    allA = D.band_bar_db(yA, nbars, E.BS)
    allB = D.band_bar_db(yB, nbars, E.BS)
    ref = max(float(np.median(allA[:D.PRE])) if len(allA) >= D.PRE else -60.0,
              float(np.median(allB[-D.POST:])) if len(allB) >= D.POST else -60.0)
    bl = [k for k in range(int(s - s0), int(e - s0))
          if 0 <= k < nbars and allA[k] > ref - 20 and allB[k] > ref - 20]
    loud = [k for k in bl if abs(allA[k] - allB[k]) < 6 and allA[k] > -40 and allB[k] > -40]
    use = loud if len(loud) >= 2 else bl
    run = longest_run(use)
    if len(run) >= 2:
        use = run
    # Once the incoming deck already carries a lock, residual xcorr often reports a
    # half-beat edge peak on later windows; prefer the near-zero cluster in that case.
    prefer_zero = bool(decks[i + 1].get('blend_lock_ms')) if i + 1 < len(decks) else False
    lag, vals = loud_lag_ms(yA, yB, bl, E.BS, E.BEAT, use, prefer_zero=prefer_zero)
    report = dict(lag_ms=None if lag is None else round(lag, 1),
                  n=len(use), n_loud=len(loud),
                  bars=[int(k + s0) for k in use],
                  offs=vals)
    return lag, report


def lock_decks(decks, trans):
    """Set incoming decks[i+1]['blend_lock_ms'] from the loud-bar lag of each blend. No-op if the flag is off."""
    if not lock_flag_on():
        return
    for i, t in enumerate(trans):
        if i + 1 >= len(decks):
            continue
        lag, report = measure_blend_lag(decks, trans, i)
        t['blend_lock'] = report
        if lag is None:
            report['applied'] = False
            if report.get('offs'):
                report['why'] = 'inconsistent / too few agreeing bars'
            continue
        if abs(lag) < LOCK_MIN_MS or abs(lag) > LOCK_MAX_MS:
            report['applied'] = False
            report['why'] = ('already locked' if abs(lag) < LOCK_MIN_MS else 'near half a beat; left to halfbeat')
            continue
        inc = decks[i + 1]
        inc['blend_lock_ms'] = round(float(inc.get('blend_lock_ms') or 0) + lag, 1)
        report['applied'] = True
        report['blend_lock_ms'] = inc['blend_lock_ms']
    if dc_flag_on():
        lock_fallback(decks, trans)


def dc_flag_on():
    import drumclash
    return drumclash.flag_on()


def lock_fallback(decks, trans):
    """DRUMCLASH=1 (2026-11-20 RCA): when the incoming's hits sit off the outgoing's 16th lattice by one constant offset
    (a flam the kick+snare-lag lock missed: 'inconsistent / too few agreeing bars') move the incoming by that offset, keep the
    move only if the off-lattice confidence drops, and record the verdict (t['drumclash']) for the hard check.
    Same sign as blend_lock_ms (A minus B, + = A late -> delay B)."""
    import blend_diag as D
    import drumclash as DC
    ev = DC.rendered_combined if DC.KIND == 'lattice' else DC.rendered_eval
    for i, t in enumerate(trans):
        if i + 1 >= len(decks):
            continue
        s0, yA, yB = D.crop_decks(dict(decks=decks, trans=trans), i)
        v = ev(yA, yB, s0, float(t['start_bar']), float(t['end_bar'])); v.pop('rows', None)
        rep = dict(before=v)
        lag = DC._lock_add(v.get('lattice', v)) if DC.KIND == 'lattice' else v.get('cluster_lag_ms')
        # only a lattice clash (constant flam) can be fixed by moving the deck; a pulse clash cannot
        if v['flagged'] and (v.get('kind') != 'pulse') and lag is not None and abs(float(decks[i + 1].get('blend_lock_ms') or 0) + lag) <= LOCK_MAX_MS:
            inc = decks[i + 1]
            inc['blend_lock_ms'] = round(float(inc.get('blend_lock_ms') or 0) + lag, 1)
            s0, yA, yB = D.crop_decks(dict(decks=decks, trans=trans), i)
            v2 = ev(yA, yB, s0, float(t['start_bar']), float(t['end_bar'])); v2.pop('rows', None)
            rep.update(applied=True, add_ms=lag, blend_lock_ms=inc['blend_lock_ms'], after=v2)
            if v2['confidence'] >= v['confidence']:  # did not help: undo, keep the original verdict
                inc['blend_lock_ms'] = round(float(inc['blend_lock_ms']) - lag, 1) or None
                if not inc['blend_lock_ms']: inc.pop('blend_lock_ms', None)
                rep.update(applied=False, why='fallback did not reduce the clash; undone')
                v2 = v
            v = v2
        rep.update(flagged=v['flagged'], level=v.get('level'), confidence=v.get('confidence'), kind=v.get('kind'))
        t['drumclash'] = rep
