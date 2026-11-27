"""BASS_WAIT (2026-11-27, OFF by default): delay the outgoing low-lane cut until the incoming
track's sub-bass is actually present, so the swap does not open a low-end hole.

'Present' means the incoming <150 Hz (or 90 Hz when that curve is passed) bar energy sits within
BASS_WAIT_DB of its drop-body level for two consecutive bars. BASS_WAIT_DB is the pro p95 of
(drop body minus incoming level at the pro's bass-swap bar) on the 33 official pro transitions.
The crossfader, window and incoming low lane stay put; only the outgoing cut is held. A PIN
swap_bars still wins. Rollback if this is ever defaulted: BASS_WAIT_OFF=1.
"""
from __future__ import annotations
import os
import numpy as np

# Filled in after calib_bass_wait.py runs on the official 33 pro transitions (see that script).
# Units: dB below the incoming drop-body (75th pct of its drop-section lows, else all-bar 75th).
BASS_WAIT_DB = 6.2  # pro p95 of (drop body - incoming 90 Hz) on official swaps already in/near drop 1 (rel -8..24, n=8). Unconditional p95 is 49.75 and is not a presence threshold (those are intro/build cues with no sub-bass).


def on(v=None):
    if str(os.environ.get('BASS_WAIT_OFF') or '').strip().lower() not in ('', '0', 'false', 'none', 'no'):
        return False
    v = os.environ.get('BASS_WAIT') if v is None else v
    try:
        return bool(int(float(v or 0)))
    except (TypeError, ValueError):
        return False


def wait_db():
    try:
        return float(os.environ.get('BASS_WAIT_DB', BASS_WAIT_DB) or BASS_WAIT_DB)
    except (TypeError, ValueError):
        return float(BASS_WAIT_DB)


def drop_body(lo, drop_bars=None):
    lo = np.asarray(lo, float)
    if drop_bars:
        vals = [float(lo[int(k)]) for k in drop_bars if 0 <= int(k) < len(lo) and np.isfinite(lo[int(k)])]
        if len(vals) >= 4:
            return float(np.percentile(vals, 75))
    fin = lo[np.isfinite(lo)]
    if fin.size < 4:
        return None
    return float(np.percentile(fin, 75))


def _src(d, mix_bar):
    fm = d.get('full_map') or []
    k = int(np.floor(float(mix_bar) - float(d['start_bar'])))
    if not (0 <= k < len(fm)):
        return None
    cell = fm[k]
    sb = cell[0] if isinstance(cell, (list, tuple)) else cell
    if sb is None:
        return None
    return int(sb)


def first_present(lo, d, start, end, body, db, hold=2):
    """First mix bar in [start, end] where `hold` consecutive incoming bars are within db of body."""
    lo = np.asarray(lo, float)
    start, end = int(np.floor(start)), int(np.ceil(end))
    run = 0
    first = None
    for b in range(start, end):
        sb = _src(d, b + 0.5)
        ok = sb is not None and 0 <= sb < len(lo) and np.isfinite(lo[sb]) and float(lo[sb]) >= body - db
        if ok:
            if run == 0:
                first = b
            run += 1
            if run >= hold:
                return first
        else:
            run, first = 0, None
    return None


def _ramp(center, up, w, n=17):
    pts = []
    for j in range(n):
        u = j / (n - 1)
        g = (1 - np.cos(np.pi * u)) / 2 if up else (1 + np.cos(np.pi * u)) / 2
        pts.append([round(float(center - w / 2 + w * u), 5), round(float(g), 5)])
    return pts


def _split_low_lane(pts, start, end):
    """Keep points outside the blend; the blend's outgoing down-ramp is replaced by the caller."""
    keep = []
    for p in pts or []:
        t = float(p[0])
        if t < start - 1e-6 or t > end + 1e-6:
            keep.append([float(p[0]), float(p[1])])
    return keep


def apply(decks, trans, lows_of, skip=(), db=None, secs_of=None):
    db = wait_db() if db is None else float(db)
    log = []
    for i, t in enumerate(trans):
        if t['a'] in skip or i + 1 >= len(decks):
            continue
        if not t.get('swap_w') or not t.get('bass_swap'):
            log.append(dict(a=t['a'], b=t['b'], wait=False, why='no swap'))
            continue
        dA, dB = decks[i], decks[i + 1]
        try:
            lo = np.asarray(lows_of(dB['id']), float)
        except Exception as ex:
            log.append(dict(a=t['a'], b=t['b'], wait=False, why=f'lows {ex}'))
            continue
        drops = None
        if secs_of:
            try:
                sec = secs_of(dB['id']) or {}
                drops = []
                for a, b in (sec.get('drops') or []):
                    drops.extend(range(int(a), int(b)))
            except Exception:
                drops = None
        body = drop_body(lo, drops)
        if body is None:
            log.append(dict(a=t['a'], b=t['b'], wait=False, why='no body'))
            continue
        s, e = float(t['start_bar']), float(t['end_bar'])
        cut0 = float(t['bass_swap'][0])
        # allow the arrival to be a little past the window (incoming drop just after the blend)
        arrived = first_present(lo, dB, s, e + 16, body, db)
        if arrived is None:
            # Never cut outgoing lows in this window; they ride the fader out.
            dA['auto']['low'] = _split_low_lane(dA.get('auto', {}).get('low'), s, e)
            t['bass_wait'] = dict(cut0=round(cut0, 3), arrived=None, delayed=True, no_cut=True, body=round(body, 2), db=db)
            t['notes'] = list(t.get('notes') or []) + [
                f'bass wait: incoming never reached body-{db:.1f} dB in the window; outgoing lows stay up'
            ]
            t['bass_swap'] = None
            t['swap_w'] = 0.0
            log.append(dict(a=t['a'], b=t['b'], wait=True, why='no incoming bass, outgoing cut skipped', body=round(body, 2)))
            continue
        arrived = float(arrived)
        if arrived <= cut0 + 0.05:
            log.append(dict(a=t['a'], b=t['b'], wait=False, why='already present', arrived=round(arrived, 2), cut0=round(cut0, 2)))
            continue
        w = float(t['swap_w'])
        # Delay the outgoing down-ramp so it starts at the arrival bar; keep width.
        new_c = arrived + w / 2.0
        # Do not run the cut past the window end.
        if new_c + w / 2.0 > e:
            new_c = max(cut0, e - w / 2.0)
            if new_c <= cut0 + 0.05:
                # Still later than the original cut: hold outgoing at 1 until window end (fade with fader).
                dA['auto']['low'] = _split_low_lane(dA.get('auto', {}).get('low'), s, e)
                t['bass_wait'] = dict(cut0=round(cut0, 3), arrived=round(arrived, 3), delayed=True, no_cut=True,
                                      body=round(body, 2), db=db)
                t['notes'] = list(t.get('notes') or []) + [
                    f'bass wait: incoming bass at bar {arrived:.1f} is past the window; outgoing lows stay up'
                ]
                t['bass_swap'] = None
                t['swap_w'] = 0.0
                log.append(dict(a=t['a'], b=t['b'], wait=True, why='arrival past window, outgoing cut skipped',
                                arrived=round(arrived, 2)))
                continue
        kept = _split_low_lane(dA.get('auto', {}).get('low'), s, e)
        dA.setdefault('auto', {})['low'] = kept + _ramp(new_c, False, w)
        new_swap = [round(new_c - w / 2.0, 3), round(new_c + w / 2.0, 3)]
        t['bass_swap'] = new_swap
        t['bass_wait'] = dict(cut0=round(cut0, 3), arrived=round(arrived, 3), delayed=True,
                              new_cut=new_swap[0], body=round(body, 2), db=db)
        t['notes'] = list(t.get('notes') or []) + [
            f'bass wait: outgoing lows held until incoming reached body-{db:.1f} dB at bar {arrived:.1f} (was {cut0:.1f})'
        ]
        log.append(dict(a=t['a'], b=t['b'], wait=True, why='delayed', arrived=round(arrived, 2),
                        cut0=round(cut0, 2), new_cut=new_swap[0], delay=round(arrived - cut0, 2)))
    return log
