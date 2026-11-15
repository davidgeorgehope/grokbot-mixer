"""TAIL_EXIT=N (2026-11-15 research, off by default): shorter outgoing tail tied to the bass swap.

the listener's 2026-11-13 blind test: he spots our blend because the outgoing fade lingers longer than the pro's.
This is a render-time post-pass on each blend's ONE logged crossfader x(t). The outgoing level may not sit
above a straight line in dB that falls RATE dB/bar (default 2.75, under the 3 dB/bar gradual-tail rule) and reaches
-24 dB at G = bass-swap end + N bars (then the outgoing is gone, x=1, as fade_long.xlong does at its exit end).
Within the gradual rule a fade from about -3 dB to -24 dB takes ~8 bars, so the line is anchored at its END:
the decline may begin before the swap ends. x_new = max(x_old, x_line): still one monotonic equal-power control,
never a cut, and where the old curve was already lower nothing changes. Never moves windows, the swap or the high
swap.

Guards are honoured, never loosened. The target exit G = swap_end + N is pushed later (0.25-bar steps) until:
- ride: outgoing above -20 dB for >= RIDE_FRAC*X - 1 bars after the bass swap ends (+0.5 bar margin),
  RIDE_FRAC 0.15 as in test_release_structure_tail.test_outgoing_fader_tail_is_gradual
- the high-swap centre (high_bar + 2) still sits at crossfader x <= 0.9 (X1)
- both bass-swap lane centres still sit at crossfader x <= 0.65 (X1)
- the incoming gain still moves <= 3 dB per beat (X1, -24 dB floor)
If the rate cap cannot reach -24 dB by G the line is simply later (gradual wins over N).
Each touched blend gets t['tail_exit'] = dict(N, rate, target_bar, exit_bar, clamped_by, old_exit_bar).
"""
import numpy as np

FLOOR = -24.0


def _db(x):
    return 20 * np.log10(np.cos(np.clip(np.asarray(x, float), 0, 1) * np.pi / 2) + 1e-9)


def _x(db):
    return float(2 / np.pi * np.arccos(min(1.0, 10 ** (db / 20))))


def line_db(b, G, rate):
    """outgoing ceiling (dB) at bar b: FLOOR at G, rising RATE dB per bar earlier, capped at 0 dB."""
    return min(0.0, FLOOR + float(rate) * (G - b))


def reshape(xs, G, rate):
    """new xfader list [[bar, x], ...]: max(x_old, x_line); x=1 from G on."""
    out = []
    for b, x in xs:
        b, x = float(b), float(x)
        L = line_db(b, G, rate)
        xl = 1.0 if b >= G - 1e-9 else (0.0 if L >= 0 else _x(L))
        out.append([b, round(max(x, xl), 5)])
    for i in range(1, len(out)):
        out[i][1] = max(out[i][1], out[i - 1][1])
    out[-1][1] = 1.0
    return out


def exit_bar(xs, floor=-30.0):
    """first logged point where the outgoing fader is under `floor` dB (or x=1)."""
    for b, x in xs:
        if x >= 1 - 1e-9 or _db(x) <= floor:
            return float(b)
    return float(xs[-1][0])


def _ok(t, xs, ride_frac, margin):
    s, e = t['start_bar'], t['end_bar']; X = e - s
    a = np.array(xs, float)
    bars = np.arange(s, e + 1e-9, 1.0)
    g = _db(np.interp(bars, a[:, 0], a[:, 1]))
    sw1 = t['bass_swap'][1]
    ride = float(np.sum(g[bars >= sw1] > -20))
    if ride < ride_frac * X - 1 + margin:
        return 'ride'
    d = np.diff(g)
    if any(v > FLOOR and dd < -3 for dd, v in zip(d, g[1:])):
        return 'rate'
    fb = np.arange(s, e + 1e-9, 1 / 16)
    gi = np.maximum(20 * np.log10(np.maximum(np.sin(np.interp(fb, a[:, 0], a[:, 1]) * np.pi / 2), 1e-6)), FLOOR)
    if len(gi) > 4 and np.abs(gi[4:] - gi[:-4]).max() > 3.0:
        return 'incoming_x1'
    if t.get('high_bar') is not None:
        hc = t['high_bar'] + 2
        if np.interp(hc, a[:, 0], a[:, 1]) > 0.9 + 1e-9:
            return 'high_swap_x'
    if t.get('bass_swap'):
        sw0, sw1 = t['bass_swap']
        for c in (sw0 + t.get('swap_w', 4) / 2, sw1 - t.get('swap_w', 4) / 2):
            if np.interp(c, a[:, 0], a[:, 1]) > 0.65 + 1e-9:
                return 'bass_swap_x'
    return None


def apply_one(t, N, rate=2.75, ride_frac=0.15, margin=0.5):
    """reshape t['xfader'] in place; returns the info dict (or None when there is no bass swap)."""
    if not t.get('bass_swap') or N is None or N <= 0:
        return None
    xs0 = [list(p) for p in t['xfader']]
    sw1 = float(t['bass_swap'][1])
    target = sw1 + float(N)
    old_exit = exit_bar(xs0, FLOOR)
    end = float(t['end_bar'])
    G, why = target, None
    if G >= old_exit:  # the old curve is already gone by then: nothing to do
        xs = xs0
    else:
        while True:
            xs = reshape(xs0, G, rate)
            bad = _ok(t, xs, ride_frac, margin)
            if not bad:
                break
            why = why or bad
            G += 0.25
            if G >= old_exit:
                xs = xs0
                break
    t['xfader'] = xs
    info = dict(N=float(N), rate=float(rate), target_bar=round(target, 3), G=round(G, 3),
                exit_bar=round(exit_bar(xs, FLOOR), 3), old_exit_bar=round(old_exit, 3),
                exit_30db_bar=round(exit_bar(xs, -30.0), 3), clamped_by=why, changed=xs is not xs0)
    t['tail_exit'] = info
    return info


def apply(decks, trans, N, rate=2.75, ride_frac=0.15, skip=()):
    """reshape every non-skipped blend and rebuild the decks' gain lanes from the new x(t) (equal-power)."""
    for t in trans:
        if t['a'] in skip:
            continue
        apply_one(t, N, rate, ride_frac)
    for i, d in enumerate(decks):
        g = []
        if i > 0:
            g += [[p[0], float(np.sin(p[1] * np.pi / 2))] for p in trans[i - 1]['xfader']]
        if i < len(decks) - 1:
            g += [[p[0], float(np.cos(p[1] * np.pi / 2))] for p in trans[i]['xfader']]
        d.setdefault('auto', {})['gain'] = g
    return trans
