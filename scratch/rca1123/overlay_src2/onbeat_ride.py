"""ONBEAT_RIDE (2026-11-23 RCA, research, off by default).

After a constant incoming lock (BLEND_LOCK or LEADIN_LOCK), residual kick
alignment can still wander bar to bar even when both decks share a perfect
metronome grid. Official 1-bar kick+snare xcorr hops on half-time-vs-regular
texture and is not used here.

This measures the kick-flux peak nearest each downbeat (search WIN_MS, default
80, well inside a half-beat at 174 BPM) on both already-rendered decks. A bar
is used only when BOTH peaks sit within OK_MS (default 40, the existing pass
line) of the downbeat — half-time bars with no on-beat kick are skipped, not
ridden. The incoming deck is then ridden so those on-beat kicks land together. Gaps
between confident bars are interpolated; the delay curve is rate-limited
(MAX_STEP ms/bar) so a single misfire cannot yank the deck. Outgoing audio
is never moved.

Sign matches blend_lock_ms: positive delay = incoming hits land later.
Does not loosen FINE_PHASE / BLEND_LOCK / 40 ms lines, write rules.json, or
change defaults.
"""
from __future__ import annotations
import os, sys
import numpy as np

WIN_MS = float(os.environ.get('ONBEAT_RIDE_WIN_MS', 80))
MAX_STEP = float(os.environ.get('ONBEAT_RIDE_MAX_STEP', 20))
MIN_CONF = int(os.environ.get('ONBEAT_RIDE_MIN_CONF', 4))
MIN_MS = float(os.environ.get('ONBEAT_RIDE_MIN_MS', 5))  # ignore jitter under this after the curve is built
PROM = float(os.environ.get('ONBEAT_RIDE_PROM', 1.8))  # peak vs median flux in the window
OK_MS = float(os.environ.get('ONBEAT_RIDE_OK_MS', 40))  # a peak farther than the 40 ms line is not an on-beat kick
HOP = 64


def flag_on(val=None):
    v = os.environ.get('ONBEAT_RIDE', '0') if val is None else val
    if v is None:
        return False
    return str(v).strip().lower() not in ('', '0', 'false', 'off', 'no')


def _flux_kick(y, sr, hop=HOP):
    from scipy.signal import butter, sosfiltfilt
    m = np.mean(y, axis=1) if np.ndim(y) > 1 else np.asarray(y, float)
    sos = butter(4, [30, 150], 'band', fs=sr, output='sos')
    z = sosfiltfilt(sos, m)
    n = len(z) // hop
    if n < 4:
        return np.zeros(1)
    e = np.sqrt((z[:n * hop].reshape(n, hop) ** 2).mean(1) + 1e-12)
    return np.maximum(np.diff(e, prepend=e[:1]), 0.0)


def kick_onbeat_ms(y, bar_in_crop, bs, sr, win_ms=WIN_MS, hop=HOP):
    """Signed ms of the kick-flux peak nearest the downbeat, or None if not confident."""
    e = getattr(kick_onbeat_ms, '_env', None)
    key = getattr(kick_onbeat_ms, '_key', None)
    this = (id(y), sr, hop)
    if key != this:
        kick_onbeat_ms._env = _flux_kick(y, sr, hop)
        kick_onbeat_ms._key = this
        e = kick_onbeat_ms._env
    fr = sr / hop
    mid = bar_in_crop * bs / hop
    rad = win_ms / 1000.0 * fr
    i0, i1 = int(round(mid - rad)), int(round(mid + rad)) + 1
    if i0 < 0 or i1 > len(e) or i1 - i0 < 4:
        return None
    w = e[i0:i1]
    med = float(np.median(w))
    peak = float(w.max())
    if peak < 1e-9 or (med > 0 and peak < PROM * med):
        return None
    j = int(np.argmax(w))
    # reject a peak glued to the window edge (likely a hop / off-beat hit)
    if j <= 1 or j >= len(w) - 2:
        return None
    # parabolic interpolation
    if 0 < j < len(w) - 1:
        a, b, c = float(w[j - 1]), float(w[j]), float(w[j + 1])
        den = a - 2 * b + c
        if den != 0:
            j = j + 0.5 * (a - c) / den
    ms = (i0 + j - mid) * 1000.0 / fr
    if abs(ms) > win_ms:
        return None
    return float(ms)


def _onbeat_one(env, bar_in_crop, bs, sr, win_ms=WIN_MS):
    fr = sr / HOP
    mid = bar_in_crop * bs / HOP
    rad = win_ms / 1000.0 * fr
    i0, i1 = int(round(mid - rad)), int(round(mid + rad)) + 1
    if i0 < 0 or i1 > len(env) or i1 - i0 < 4:
        return None
    w = env[i0:i1]
    med = float(np.median(w))
    peak = float(w.max())
    if peak < 1e-9 or (med > 0 and peak < PROM * med):
        return None
    j = int(np.argmax(w))
    if j <= 1 or j >= len(w) - 2:
        return None
    if 0 < j < len(w) - 1:
        a, b, c = float(w[j - 1]), float(w[j]), float(w[j + 1])
        den = a - 2 * b + c
        if den != 0:
            j = j + 0.5 * (a - c) / den
    ms = (i0 + j - mid) * 1000.0 / fr
    if abs(ms) > win_ms:
        return None
    return float(ms)


def measure(yA, yB, s0, start, end, bs, sr, win_ms=WIN_MS):
    envA = _flux_kick(yA, sr)
    envB = _flux_kick(yB, sr)
    out = []
    for mb in range(int(start), int(end)):
        a = _onbeat_one(envA, mb - s0, bs, sr, win_ms)
        b = _onbeat_one(envB, mb - s0, bs, sr, win_ms)
        have = a is not None and b is not None
        onbeat = have and abs(a) <= OK_MS and abs(b) <= OK_MS
        out.append(dict(mix_bar=int(mb),
                        a_ms=None if a is None else round(a, 1),
                        b_ms=None if b is None else round(b, 1),
                        residual_ms=None if not have else round(a - b, 1),
                        conf=bool(onbeat)))
    return out



def curve(recs, start, end, max_step=MAX_STEP):
    """Delay (ms) to apply to incoming at each mix bar: interp + rate limit."""
    xs = [r['mix_bar'] for r in recs if r.get('conf')]
    ys = [r['residual_ms'] for r in recs if r.get('conf')]
    bars = list(range(int(start), int(end)))
    if len(xs) < MIN_CONF:
        return {b: 0.0 for b in bars}, dict(why=f'too few confident bars ({len(xs)} < {MIN_CONF})', n_conf=len(xs))
    raw = np.interp(bars, xs, ys)
    # hold the first/last confident value outside the confident span (np.interp already does)
    # rate-limit first differences
    out = [float(raw[0])]
    for v in raw[1:]:
        prev = out[-1]
        dv = v - prev
        if dv > max_step:
            dv = max_step
        elif dv < -max_step:
            dv = -max_step
        out.append(prev + dv)
    # pull the rate-limited curve back toward observations where they agree
    # (already starts from interp; step cap is the only smoothing)
    delays = {b: round(float(d), 1) for b, d in zip(bars, out)}
    # if the whole curve is under MIN_MS, do not move the deck
    med = float(np.median([abs(delays[b]) for b in bars]))
    info = dict(n_conf=len(xs), conf_bars=xs, conf_residual=[round(float(v), 1) for v in ys],
                median_abs=round(med, 1), max_abs=round(max(abs(delays[b]) for b in bars), 1),
                max_step=max_step)
    if med < MIN_MS and max(abs(delays[b]) for b in bars) < max(MIN_MS * 2, 10):
        info['applied'] = False
        info['why'] = 'residual already under MIN_MS'
        return {b: 0.0 for b in bars}, info
    info['applied'] = True
    return delays, info


def warp(y, s0, delays, bs, sr):
    """Delay incoming samples by the per-bar curve (linear interp of a time map)."""
    y = np.asarray(y, np.float32)
    n = len(y)
    if not delays:
        return y
    t_bar = s0 + np.arange(n) / bs
    bars = np.array(sorted(delays), float)
    vals = np.array([delays[int(b)] for b in bars], float)
    # extend edges
    delay_ms = np.interp(t_bar, bars, vals)
    # y_new[i] = y[i - delay*sr]  (positive delay = later)
    src = np.arange(n) - delay_ms / 1000.0 * sr
    out = np.empty_like(y)
    idx = np.arange(n, dtype=np.float64)
    for ch in range(y.shape[1] if y.ndim == 2 else 1):
        col = y[:, ch] if y.ndim == 2 else y
        interp = np.interp(src, idx, col, left=0.0, right=0.0).astype(np.float32)
        if y.ndim == 2:
            out[:, ch] = interp
        else:
            out = interp
    return out


def apply_to_pair(yA, yB, s0, start, end, bs, sr):
    """Warp incoming (yB) to lock on-beat kicks to outgoing. Returns (yB2, report)."""
    if not flag_on():
        return yB, dict(applied=False, why='flag off')
    recs = measure(yA, yB, s0, start, end, bs, sr)
    delays, info = curve(recs, start, end)
    report = dict(info, bars=recs, delays={str(k): v for k, v in delays.items() if v})
    if not info.get('applied'):
        print('ONBEAT_RIDE skipped', info, file=sys.stderr, flush=True)
        return yB, report
    yB2 = warp(yB, s0, delays, bs, sr)
    after = measure(yA, yB2, s0, start, end, bs, sr)
    conf = [r['residual_ms'] for r in after if r.get('conf')]
    report['after'] = dict(n_conf=len(conf),
                           residual=[round(float(v), 1) for v in conf],
                           median=None if not conf else round(float(np.median(conf)), 1),
                           mean=None if not conf else round(float(np.mean(conf)), 1),
                           max_abs=None if not conf else round(float(np.max(np.abs(conf))), 1),
                           std=None if not conf else round(float(np.std(conf)), 1))
    report['applied'] = True
    print('ONBEAT_RIDE applied n_conf', info.get('n_conf'),
          'median_abs', info.get('median_abs'), 'after', report['after'],
          file=sys.stderr, flush=True)
    return yB2, report


_HOOKED = False

def install_engine_hook():
    """Make later render_deck calls (blend_diag.crop_decks / figure) apply stored delays."""
    global _HOOKED
    if _HOOKED:
        return
    import engine
    orig = engine.render_deck
    def hooked(d):
        y = orig(d)
        raw = d.get('onbeat_delays_mix')
        if not raw:
            return y
        delays = {int(k): float(v) for k, v in raw.items()}
        from engine import BS, SR
        return warp(y, d['start_bar'], delays, BS, SR)
    engine.render_deck = hooked
    _HOOKED = True
