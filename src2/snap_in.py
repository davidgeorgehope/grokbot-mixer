"""SNAP_IN (2026-11-15 research, off by default): late, fast incoming rise + shallow outgoing hold.

Today's Hybrid Minds UKF pick (Jome Cinnamon Remix -> Logistics Together): the pro's incoming
reaches near-full around the bass swap in about 2 bars, then the outgoing sits around -10..-15 dB
for a long stretch underneath. Our FADE=long default starts a 16-bar window early and dumps the
outgoing under -12 dB about 8 bars later. Corpus: 10/33 admitted pros have this combo
(incoming -18->-6 dB in <=2 bars, then >=8 audible outgoing bars).

Off by default and not a global rule: the listener (2026-11-15) noted that some blends are quick and some last ages, depending on the tracks. Use this as a per-pair option (incoming already in a drop, outgoing in a breakdown or already down in bass, enough of the outgoing left to linger), not on every blend.

This post-pass rebuilds the one monotonic equal-power x(t):
- delay the incoming rise until the last legal moment before the bass-swap centre
- rise linearly in incoming dB at most RISE dB/beat (default 2.95, under the X1 3.0 cap, -24 dB floor)
  so the swap centre still sits at x in [0.2, 0.65]
- after the later swap centre, continue to a hold where the outgoing is HOLD_DB (default -12)
- hold, then exit at most RATE dB/bar (default 2.75, under the 3 dB/bar gradual-tail rule)
  with an optional short residual past the window (EXT_CAP, default 8 bars) so the hold is not
  chopped to silence at end_bar
Never moves the window start, the bass swap or the high swap. Guards (ride, rate, X1 incoming,
swap-x, high-swap-x) are honoured, never loosened: if a true 1-bar slam would break X1, the rise
is the fastest legal even rise instead (clamped_by records that). Each touched blend gets
t['snap_in'] = dict(...).
"""
import numpy as np
import tail_exit as TE

FLOOR = -24.0
RISE = 2.95          # dB / beat, under X1's 3.0
RATE = 2.75          # dB / bar outgoing exit, under the 3 dB/bar gradual-tail rule
HOLD_DB = -12.0
EXT_CAP = 8.0
STEP = 1.0 / 16.0  # X1 samples at 1/16 bar; linear-x interp on a coarser grid invents steep dB steps
X_SWAP_MAX = 0.65
X_SWAP_MIN = 0.20
X_HIGH_MAX = 0.90


def _in_db(x):
    return 20 * np.log10(np.sin(np.clip(np.asarray(x, float), 0, 1) * np.pi / 2) + 1e-9)


def _out_db(x):
    return TE._db(x)


def _x_from_in(db):
    return float(2 / np.pi * np.arcsin(min(1.0, 10 ** (float(db) / 20))))


def _x_from_out(db):
    return TE._x(db)


def _beats_for_in_rise(target_db, rise=RISE, floor=FLOOR):
    return max(0.0, (float(target_db) - float(floor)) / max(float(rise), 1e-9))


def _bars_for_in_rise(target_db, rise=RISE, floor=FLOOR):
    return _beats_for_in_rise(target_db, rise, floor) / 4.0


def swap_centres(t):
    if not t.get('bass_swap'):
        return []
    sw0, sw1 = float(t['bass_swap'][0]), float(t['bass_swap'][1])
    w = float(t.get('swap_w') or max(sw1 - sw0 - 1.0, 1.0))
    return [sw0 + w / 2.0, sw1 - w / 2.0]


def _grid(t, end):
    s = float(t['start_bar'])
    bars = np.arange(s, float(end) + 1e-9, STEP)
    if not len(bars) or bars[-1] < float(end) - 1e-9:
        bars = np.append(bars, float(end))
    return bars


def _advance(x, dt, rise, rate, x_cap, x_hold, floor):
    """Largest legal x after dt bars: incoming <= rise dB/beat, outgoing <= rate dB/bar."""
    if dt <= 0:
        return min(x, x_cap, x_hold)
    inc = max(float(_in_db(x)), floor)
    x_in = _x_from_in(min(0.0, inc + rise * 4.0 * dt))
    out = float(_out_db(x))
    out2 = out - rate * dt
    if out2 >= 0:
        x_out = 0.0
    elif out2 <= floor:
        x_out = 1.0
    else:
        x_out = _x_from_out(out2)
    return min(max(x, min(x_in, x_out)), x_cap, x_hold, 1.0)


def _build(t, hold_db, rise, rate, ext_cap, floor, hold_extra=0):
    """Return xfader list and an info dict (no guards yet)."""
    s, e0 = float(t['start_bar']), float(t['end_bar'])
    xs0 = [list(p) for p in t['xfader']]
    old_exit = TE.exit_bar(xs0, floor)
    centres = swap_centres(t)
    x_hold = _x_from_out(hold_db)
    x_floor = _x_from_in(floor)  # incoming at -24 dB, not x=0 (avoids a floor-clipped 1-beat jump)

    # Start the rise late enough that a legal incoming+outgoing rise reaches x=0.65
    # at the first swap centre (top of X1's legal swap window).
    if centres:
        first_c, last_c = min(centres), max(centres)
        # outgoing 0 dB -> -5.64 dB at `rate` dB/bar is usually the tighter cap
        need_out = max(0.0, (0.0 - float(_out_db(X_SWAP_MAX))) / max(rate, 1e-9))
        need_in = _bars_for_in_rise(float(_in_db(X_SWAP_MAX)), rise, floor)
        t_rise0 = first_c - max(need_out, need_in)
        t_rise0 = max(t_rise0, s)
    else:
        first_c = last_c = None
        t_rise0 = s

    # After the later centre, outgoing falls from ~-5.6 dB to hold_db at `rate`
    after = max(0.0, (float(_out_db(X_SWAP_MAX)) - hold_db) / max(rate, 1e-9))
    t_hold_ready = (last_c + after) if last_c is not None else (t_rise0 + max(
        _bars_for_in_rise(float(_in_db(x_hold)), rise, floor),
        (0.0 - hold_db) / max(rate, 1e-9)))

    exit_len = (hold_db - floor) / max(rate, 1e-9)
    hold_extra = max(0.0, float(hold_extra or 0))
    # 32-bar FADE=long solos keep their early exit and are not extended
    if old_exit >= e0 - 2.0 - 1e-9:
        # Plateau at hold_db until e0+hold_extra (default 0, so the residual
        # still starts near the window end), then the usual rate-limited exit.
        # ext_cap still bounds a zero-extra residual; a requested plateau may
        # run longer than ext_cap but never loosens the dB/beat or dB/bar caps.
        max_ext = max(float(ext_cap), hold_extra + exit_len)
        t_exit0 = max(t_hold_ready, e0 + hold_extra)
        G = t_exit0 + exit_len
        if G > e0 + max_ext:
            G = e0 + max_ext
            t_exit0 = G - exit_len
        if t_exit0 < t_hold_ready:
            G = min(t_hold_ready + exit_len, e0 + max_ext)
            t_exit0 = G - exit_len
    else:
        G = old_exit
        t_exit0 = G - exit_len
        if t_exit0 < t_hold_ready:
            t_exit0 = t_hold_ready
            G = min(t_exit0 + exit_len, old_exit)

    # include the exact rise / exit / centre / end points in the grid
    bars = set(float(b) for b in _grid(t, G))
    for b in (t_rise0, t_exit0, G, first_c, last_c):
        if b is not None and s - 1e-9 <= b <= G + 1e-9:
            bars.add(float(b))
    if t.get('high_bar') is not None:
        bars.add(float(t['high_bar']) + 2.0)
    bars = sorted(bars)

    xs = []
    x = 0.0
    prev = s
    hc = (float(t['high_bar']) + 2.0) if t.get('high_bar') is not None else None
    for b in bars:
        dt = b - prev
        if b < t_rise0 - 1e-9:
            x = 0.0
        elif b >= G - 1e-9:
            x = 1.0
        elif b >= t_exit0 - 1e-9:
            out = hold_db - rate * (b - t_exit0)
            x = 1.0 if out <= floor else (0.0 if out >= 0 else _x_from_out(out))
        else:
            cap = x_hold
            if last_c is not None and b <= last_c + 1e-9:
                cap = min(cap, X_SWAP_MAX)
            if hc is not None and abs(b - hc) <= 0.5:
                cap = min(cap, X_HIGH_MAX)
            if abs(b - t_rise0) <= 1e-9:
                x = min(x_floor, cap)
            else:
                x = _advance(x, dt, rise, rate, cap, x_hold, floor)
        xs.append([round(float(b), 5), round(float(x), 5)])
        prev = b
    for i in range(1, len(xs)):
        xs[i][1] = max(xs[i][1], xs[i - 1][1])
    xs[-1][1] = 1.0
    if xs[0][0] > s + 1e-9:
        xs = [[round(s, 5), 0.0]] + xs
    xs[0][1] = 0.0
    info = dict(hold_db=float(hold_db), rise=float(rise), rate=float(rate),
                t_rise0=round(float(t_rise0), 3), t_exit0=round(float(t_exit0), 3),
                G=round(float(G), 3), x_hold=round(float(x_hold), 4),
                old_exit_bar=round(float(old_exit), 3),
                hold_extra=round(float(hold_extra), 3),
                exit_bar=round(TE.exit_bar(xs, floor), 3),
                extended_by=round(float(max(0.0, G - e0)), 3))
    return xs, info


def apply_one(t, hold_db=HOLD_DB, rise=RISE, rate=RATE, ext_cap=EXT_CAP,
              floor=FLOOR, ride_frac=0.15, margin=0.5, hold_extra=0):
    if hold_db is None or hold_db == 0 or not t.get('xfader'):
        return None
    hold_db = -abs(float(hold_db))
    if hold_db >= 0:
        return None
    # never above the X1 3.0 dB/beat cap, even if a caller asks for a slam
    rise = min(float(rise), 3.0)
    xs0 = [list(p) for p in t['xfader']]
    e0 = float(t['end_bar'])
    xs, info = _build(t, hold_db, rise, rate, ext_cap, floor, hold_extra=hold_extra)
    inside = [p for p in xs if p[0] <= e0 + 1e-9] or xs
    why = TE._ok(t, inside, ride_frac, margin)
    # also check the residual, if any, for incoming X1 + outgoing rate
    if not why and xs[-1][0] > e0 + 1e-9:
        t_ext = dict(t, end_bar=xs[-1][0])
        why = TE._ok(t_ext, xs, ride_frac, margin)
        # swap/high centres are inside the original window; a residual-only
        # 'ride' fail after we already held above -20 is not a reason to abort
        if why == 'ride':
            why = None
    if why:
        xs = xs0
        info = dict(hold_db=float(hold_db), rise=float(rise), rate=float(rate),
                    old_exit_bar=round(TE.exit_bar(xs0, floor), 3),
                    exit_bar=round(TE.exit_bar(xs0, floor), 3),
                    extended_by=0.0, clamped_by=why, changed=False)
        t['xfader'] = xs
        t['snap_in'] = info
        return info
    # residual is part of this blend
    if xs[-1][0] > e0 + 1e-9:
        t['end_bar'] = float(xs[-1][0])
    t['xfader'] = xs
    changed = len(xs) != len(xs0) or any(
        abs(a[0] - b[0]) > 1e-6 or abs(a[1] - b[1]) > 1e-6 for a, b in zip(xs, xs0))
    info.update(clamped_by=None, changed=bool(changed),
                exit_bar=round(TE.exit_bar(xs, floor), 3))
    t['snap_in'] = info
    return info


def _extend_outgoing(decks, trans):
    import tail_shape as TS
    TS._extend_outgoing(decks, trans)


def apply(decks, trans, hold_db=HOLD_DB, rise=RISE, rate=RATE, ext_cap=EXT_CAP,
          floor=FLOOR, ride_frac=0.15, skip=(), hold_extra=0):
    for i, t in enumerate(trans):
        if t['a'] in skip:
            continue
        apply_one(t, hold_db, rise, rate, ext_cap, floor, ride_frac, hold_extra=hold_extra)
        if i + 1 < len(trans) and t['end_bar'] > trans[i + 1]['start_bar']:
            nxt = trans[i + 1]['start_bar']
            t['xfader'] = [p for p in t['xfader'] if p[0] <= nxt + 1e-9]
            if t['xfader'] and t['xfader'][-1][1] < 1 - 1e-9:
                t['xfader'].append([float(nxt), 1.0])
            t['end_bar'] = float(t['xfader'][-1][0])
            if t.get('snap_in'):
                t['snap_in']['capped_by_next'] = True
                t['snap_in']['exit_bar'] = round(TE.exit_bar(t['xfader'], floor), 3)
    _extend_outgoing(decks, trans)
    for i, d in enumerate(decks):
        g = []
        if i > 0:
            g += [[p[0], float(np.sin(p[1] * np.pi / 2))] for p in trans[i - 1]['xfader']]
        if i < len(decks) - 1:
            g += [[p[0], float(np.cos(p[1] * np.pi / 2))] for p in trans[i]['xfader']]
        d.setdefault('auto', {})['gain'] = g
    return trans
