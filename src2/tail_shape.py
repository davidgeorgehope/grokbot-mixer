"""TAIL_SHALLOW=R (2026-11-15 research, off by default): shallower outgoing fade after the bass swap.

Pro NNLS outgoing curves (tail_curves.py, 2026-11-15): after the bass swap the median pro stays
near -3 dB at the swap, about -10 dB at +8 bars and about -14 dB at +16, i.e. a ~1 dB/bar decline
with a long mid-level residual (audible-zone median 14 bars). Our FADE=long default is already
quieter at the swap (median -7 dB) and dumps at ~2.6 dB/bar to silence by +6 (audible-zone median
4 bars). the listener's 2026-11-13 note on hybrid_minds_ukf__12 (pro stays around -2..-4 dB for the whole
window; ours is gone by +4) is the same shape, not a longer raw tail — a shorter TAIL_EXIT slightly
hurt that pair and was a no-op or a loss on held-out once ride/rate guards were honoured.

This post-pass lifts the outgoing (lowers x) so it never falls faster than R dB/bar after the exit
starts, and extends the outgoing deck past the window until the line reaches FLOOR (-24 dB) instead
of snapping to silence at end_bar. Still one monotonic equal-power control. Never moves the window,
the bass swap or the high swap. Guards (ride, 3 dB/bar, X1, swap-x) are honoured, never loosened.
Each touched blend gets t['tail_shape'] = dict(rate, floor, old_exit_bar, exit_bar, extended_by, changed).

TAIL_SHALLOW_CAP=N / TAIL_SHALLOW_GATE=end (2026-11-16 research, off by default; only act with TAIL_SHALLOW=R):
the uncapped residual overfit (R=1 train +2.13 / held-out -1.36; the long ~13-bar extension helped pairs whose
pro stays in and hurt pairs whose pro already cut). CAP bounds the residual to N bars past the planned window end:
the outgoing target is the louder-is-not-allowed min of (a) the shallow R dB/bar line from the exit start and
(b) a deadline line that falls CAP_RATE (2.75 dB/bar, under the 3 dB/bar gradual rule) and reaches FLOOR exactly
at end_bar + N. So the mid-fade is lifted, then the residual still leaves gradually and is gone by end + N.
The outgoing is only ever lifted (x = min(x_old, x_target)); upper envelope of two <=3 dB/bar curves stays <=3.
GATE=end: only touch blends whose designed exit (outgoing at FLOOR) already sits within GATE_TOL bars of the
window end (the typical 16-bar case); FADE=long 32-bar solos (exit LONG_SOLO bars before the end) are left alone.
Info adds cap, gate, gated_out.
"""
import numpy as np
import tail_exit as TE

FLOOR = -24.0
STEP = 0.25
EXT_CAP = 16.0  # bars past the original window end
CAP_RATE = 2.75  # dB/bar for the capped residual's final leave (TAIL_SHALLOW_CAP)
GATE_TOL = 2.0   # bars: TAIL_SHALLOW_GATE=end needs the designed exit within this of end_bar


def _extend_points(xs, G, rate, start_b, start_db):
    """xfader from the original points, then 0.25-bar steps until bar G (outgoing at FLOOR)."""
    out = [list(p) for p in xs]
    last_b = out[-1][0]
    b = last_b + STEP
    while b <= G + 1e-9:
        db = start_db - float(rate) * (b - start_b)
        x = 1.0 if db <= FLOOR else (0.0 if db >= 0 else TE._x(db))
        out.append([round(b, 5), round(x, 5)])
        b += STEP
    if out[-1][0] < G - 1e-9:
        out.append([round(G, 5), 1.0])
    # monotonic and not louder-outgoing than allowed by the line (x only rises)
    for i in range(1, len(out)):
        out[i][1] = max(out[i][1], out[i - 1][1])
    return out


def reshape(xs, rate, floor=FLOOR):
    """lift outgoing so the post-exit fall is at most `rate` dB/bar; extend until `floor`."""
    xs = [list(p) for p in xs]
    if not xs:
        return xs, 0.0
    bars = np.array([p[0] for p in xs], float)
    g = TE._db(np.array([p[1] for p in xs], float))
    # exit start: last point still at/above -3.5 dB (the FADE=long plateau is ~-1.4..-3 dB), else first point
    plat = np.flatnonzero(g >= -3.5)
    i0 = int(plat[-1]) if len(plat) else 0
    b0, db0 = float(bars[i0]), float(g[i0])
    out = []
    for b, x in xs:
        b, x = float(b), float(x)
        if b <= b0 + 1e-9:
            out.append([b, x])
            continue
        line = db0 - float(rate) * (b - b0)
        # lift outgoing (lower x) up to the shallow line; never lower it
        if line >= 0:
            xl = 0.0
        elif line <= floor:
            xl = 1.0
        else:
            xl = TE._x(line)
        out.append([b, round(min(x, xl), 5)])
    last_b, last_x = out[-1]
    last_db = float(TE._db(last_x))
    extended = 0.0
    if last_db > floor + 1e-9:
        # bars needed to reach the floor at `rate`, capped
        need = (last_db - floor) / max(float(rate), 1e-9)
        G = min(last_b + need, last_b + EXT_CAP)
        # re-anchor the extension at the exit start so the line stays consistent
        out = _extend_points(out, G, rate, b0, db0)
        extended = round(out[-1][0] - last_b, 3)
    for i in range(1, len(out)):
        out[i][1] = max(out[i][1], out[i - 1][1])
    return out, extended


def _target_db(b, b0, db0, rate, G, cap_rate):
    return min(db0 - float(rate) * (b - b0), FLOOR + float(cap_rate) * (G - b))


def reshape_capped(xs, rate, end_bar, cap, floor=FLOOR, cap_rate=CAP_RATE):
    """shallow R line from the exit start, but the residual must reach `floor` by end_bar + cap
    (final leave at <= cap_rate dB/bar). Only ever lifts the outgoing inside the window."""
    xs = [list(p) for p in xs]
    if not xs:
        return xs, 0.0
    bars = np.array([p[0] for p in xs], float)
    g = TE._db(np.array([p[1] for p in xs], float))
    plat = np.flatnonzero(g >= -3.5)
    i0 = int(plat[-1]) if len(plat) else 0
    b0, db0 = float(bars[i0]), float(g[i0])
    G = float(end_bar) + float(cap)

    def xt(b):
        db = _target_db(b, b0, db0, rate, G, cap_rate)
        return 0.0 if db >= 0 else (1.0 if db <= floor + 1e-9 else TE._x(db))
    out = []
    for b, x in xs:
        b, x = float(b), float(x)
        out.append([b, x] if b <= b0 + 1e-9 else [b, round(min(x, xt(b)), 5)])
    last_b = out[-1][0]
    extended = 0.0
    if out[-1][1] < 1 - 1e-9:
        b = last_b + STEP
        while b < G - 1e-9:
            x = round(xt(b), 5)
            out.append([round(b, 5), x])
            if x >= 1 - 1e-9:
                break
            b += STEP
        if out[-1][1] < 1 - 1e-9:
            out.append([round(G, 5), 1.0])
        extended = round(out[-1][0] - last_b, 3)
    for i in range(1, len(out)):
        out[i][1] = max(out[i][1], out[i - 1][1])
    return out, extended


def gate_end(t, floor=FLOOR, tol=GATE_TOL):
    """True when the designed exit (outgoing at floor) already sits at the window end."""
    return (float(t['end_bar']) - TE.exit_bar(t['xfader'], floor)) <= tol + 1e-9


def apply_one(t, rate, floor=FLOOR, ride_frac=0.15, margin=0.5, cap=None, gate=None):
    if rate is None or rate <= 0 or not t.get('xfader'):
        return None
    xs0 = [list(p) for p in t['xfader']]
    old_exit = TE.exit_bar(xs0, floor)
    if gate == 'end' and not gate_end(t, floor):
        info = dict(rate=float(rate), floor=float(floor), old_exit_bar=round(old_exit, 3),
                    exit_bar=round(old_exit, 3), extended_by=0.0, clamped_by=None, changed=False,
                    cap=cap, gate=gate, gated_out=True)
        t['tail_shape'] = info
        return info
    if cap is not None and cap > 0:
        xs, extended = reshape_capped(xs0, rate, t['end_bar'], cap, floor)
    else:
        xs, extended = reshape(xs0, rate, floor)
    # guards are checked on the original window only (end_bar is unchanged)
    inside = [p for p in xs if p[0] <= t['end_bar'] + 1e-9] or xs
    why = TE._ok(t, inside, ride_frac, margin)
    if why:
        xs, extended = xs0, 0.0
    t['xfader'] = xs
    # residual is part of this blend: x reaches 1 at the extended end so X1's 0->1 still holds
    if (not why) and xs[-1][0] > t['end_bar'] + 1e-9:
        t['end_bar'] = float(xs[-1][0])
    changed = (not why) and (len(xs) != len(xs0) or any(
        abs(a[0] - b[0]) > 1e-6 or abs(a[1] - b[1]) > 1e-6 for a, b in zip(xs, xs0)))
    info = dict(rate=float(rate), floor=float(floor),
                old_exit_bar=round(old_exit, 3),
                exit_bar=round(TE.exit_bar(xs, floor), 3),
                extended_by=extended, clamped_by=why, changed=bool(changed))
    if cap is not None or gate is not None:
        info.update(cap=cap, gate=gate, gated_out=False)
    t['tail_shape'] = info
    return info


def _extend_outgoing(decks, trans):
    """keep playing the outgoing source past the window so a residual can decay."""
    for i, t in enumerate(trans):
        last = float(t['xfader'][-1][0])
        d = decks[i]
        need = int(np.ceil(last - 1e-9)) - int(d['end_bar'])
        if need <= 0:
            continue
        fm = d['full_map']
        src, kind = fm[-1]
        for k in range(1, need + 1):
            fm.append([src + k, kind])
        d['end_bar'] = d['start_bar'] + len(fm)
        d['map'] = fm[:1] + fm[-1:]


def apply(decks, trans, rate, floor=FLOOR, ride_frac=0.15, skip=(), cap=None, gate=None):
    for i, t in enumerate(trans):
        if t['a'] in skip:
            continue
        apply_one(t, rate, floor, ride_frac, cap=cap, gate=gate)
        # do not run a residual into the next blend
        if i + 1 < len(trans) and t['end_bar'] > trans[i + 1]['start_bar']:
            nxt = trans[i + 1]['start_bar']
            t['xfader'] = [p for p in t['xfader'] if p[0] <= nxt + 1e-9]
            if t['xfader'] and t['xfader'][-1][1] < 1 - 1e-9:
                t['xfader'].append([float(nxt), 1.0])
            t['end_bar'] = float(t['xfader'][-1][0])
            if t.get('tail_shape'):
                t['tail_shape']['capped_by_next'] = True
                t['tail_shape']['exit_bar'] = round(TE.exit_bar(t['xfader'], floor), 3)
    _extend_outgoing(decks, trans)
    for i, d in enumerate(decks):
        g = []
        if i > 0:
            g += [[p[0], float(np.sin(p[1] * np.pi / 2))] for p in trans[i - 1]['xfader']]
        if i < len(decks) - 1:
            g += [[p[0], float(np.cos(p[1] * np.pi / 2))] for p in trans[i]['xfader']]
        d.setdefault('auto', {})['gain'] = g
    return trans
