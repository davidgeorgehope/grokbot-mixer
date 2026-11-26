"""EARLY_EXIT=1 (2026-11-25, off by default): principled post-drop-1 breakdown blend shape.

Pro pattern (corpus_v2 bd_post_d1 n=84 + hybrid_minds_ukf__28/10/13):
- Enter during the outgoing track's post-drop-1 breakdown with the incoming track's intro
  rising smoothly up to its drop1 (36-44 bar total blend, e.g. X=36, 40, 44).
- Drop-anchored bass handoff: outgoing stays full (~-1.3 dB) with its bass intact up to
  incoming drop1 (avoiding pre-drop bass holes & pumping); incoming bass ramps 0->1 over
  [k_drop-2, k_drop] (x~0.34 at centre), outgoing bass ramps 1->0 over [k_drop-0.5, k_drop+2.5]
  (x~0.58 at centre, both inside X1's [0.20, 0.65]).
- Outgoing deck drops smoothly (<= 2.65 dB/bar, under the 3.0 dB/bar cap) to ~-15 dB ONLY AFTER
  incoming drop1 lands, holds there, and exits smoothly to -24 dB -> x=1.0 by blend end.
- Honours X1, C2, L1, O1, N1, and gradual-tail rules; never modifies defaults when off.
"""
import os
import numpy as np
import tail_exit as TE

FLOOR = -24.0
HOLD_DB = -14.0
PRE_EXP = 1.8        # convex pre-drop fade-in exponent so early intro dips aren't exposed and stalled before drop1
HOLD_RATE = 1.15     # dB / bar outgoing fade after drop1 -> -14 dB (~8.5 bars after k_drop), matching ~20-26 bar pro blend length
RATE = 2.65          # dB / bar max outgoing rate (exit ramp), strictly under the 3.0 dB/bar rule
RISE_CAP = 2.90      # dB / beat incoming rise, strictly under X1's 3.0 cap
STEP = 1.0 / 16.0    # X1 evaluates at 1/16 bar
X_SW_IN = 0.34       # x at incoming low-swap centre (k_drop - 1.0; A=-1.3dB, B=-5.9dB)
X_SW_OUT = 0.58      # x at outgoing low-swap centre (k_drop + 1.0; A=-4.3dB, B=-2.0dB)
X_HOLD_MAX = 0.895   # <= 0.90 so any high swap before hold stays valid
MIN_REM_BARS = 24.0  # fewest outgoing bars skipped to qualify as an early exit
MIN_BLEND_BARS = 36.0         # bare EARLY_EXIT=1 threshold so base X<=32 never drifts
MIN_PICKER_BLEND_BARS = 20.0  # picker-nominated breakdown blends (20..44 bars fit bounded breakdowns before Drop 2)


def flag_on(env=None):
    v = (env or os.environ).get('EARLY_EXIT', '0')
    return str(v).strip().lower() in ('1', 'true', 'yes', 'on')


def _in_db(x):
    return float(20.0 * np.log10(np.sin(np.clip(float(x), 0.0, 1.0) * np.pi / 2.0) + 1e-9))


def _out_db(x):
    return float(TE._db(x))


def _x_from_in(db):
    return float(2.0 / np.pi * np.arcsin(min(1.0, 10.0 ** (float(db) / 20.0))))


def _x_from_out(db):
    return float(TE._x(db))


def _ramp(c, up, w=2.0):
    return [[round(c - w / 2.0 + w * j / 16.0, 5),
             round(float((1.0 - np.cos(np.pi * j / 16.0)) / 2.0 if up else (1.0 + np.cos(np.pi * j / 16.0)) / 2.0), 5)]
            for j in range(17)]


def next_drop_after(sa, s_bar):
    """Start bar of the outgoing track's next real drop/section restart after s_bar, or None."""
    if not sa:
        return None
    s_bar = float(s_bar)
    cands = []
    for ds, de in (sa.get('drops') or []):
        ds, de = float(ds), float(de)
        if ds >= 16.0 and (de - ds) >= 16.0 and ds > s_bar + 1e-6:
            cands.append(ds)
    for ph in (sa.get('phases') or []):
        if ph.get('name') == 'drop':
            ds, de = float(ph.get('start', 0)), float(ph.get('end', 0))
            if ds >= 16.0 and (de - ds) >= 16.0 and ds > s_bar + 1e-6:
                cands.append(ds)
    return min(cands) if cands else None


def fits_before_next_drop(sa, s_bar, e_bar):
    """True when the blend finishes before the outgoing track's next drop/section restart."""
    dn = next_drop_after(sa, s_bar)
    return dn is None or float(e_bar) <= dn + 1e-6


def _eligible_blend(t, decks, i, secs_of):
    """True when blend i is a genuine early-exit (outgoing has >=24 bars left after blend end)."""
    if t.get('fade') == 'graphcut':
        return False
    s, e = float(t['start_bar']), float(t['end_bar'])
    X = e - s
    min_x = MIN_PICKER_BLEND_BARS if t.get('early_exit_cand') else MIN_BLEND_BARS
    if X < min_x - 1e-9:
        return False
    A = decks[i]
    sa = secs_of(A['id']) if secs_of else {}
    na = float(sa.get('music_end') or sa.get('n_bars') or 999)
    out_end = A['full_map'][-1][0] + 1 if A.get('full_map') else 999
    if na - out_end < MIN_REM_BARS:
        return False
    return True


def _k_drop_in_blend(t, decks, i, secs_of):
    """Bar offset inside [0, X] where incoming track's drop1 lands (or sensible mid-blend anchor)."""
    s, e = float(t['start_bar']), float(t['end_bar'])
    X = e - s
    B = decks[i + 1]
    sb = secs_of(B['id']) if secs_of else {}
    d1_b = sb.get('drop1')
    ib = B['full_map'][0][0] if B.get('full_map') else 0
    if d1_b is not None:
        k_drop = float(d1_b) - float(ib)
        if 4.0 <= k_drop <= X - 8.5:
            return k_drop
    return min(16.0, max(8.0, round(X * 0.4)))


def build_xfader(s, e, k_drop, hold_db=HOLD_DB, rate=RATE, sw_in=2.0, sw_out=3.0):
    """Construct monotonic X1-compliant xfader x(t) and drop-anchored bass swap timing."""
    X = float(e - s)
    hold_db = -abs(float(hold_db))
    # Clamp k_drop so pre-drop rise (>=4 bars) and post-drop hold+exit (>=10 bars) fit cleanly inside X
    k_d = float(np.clip(k_drop, 4.0, max(4.0, X - 9.0)))
    c_in = s + k_d - sw_in / 2.0      # incoming bass finishes 0->1 right at k_drop
    c_out = s + k_d + 1.0             # outgoing bass ramps 1->0 over [k_d - 0.5, k_d + 2.5]
    if c_in < s + 3.0:
        c_in = s + 3.0
        c_out = c_in + 2.0
    sw_c = 0.5 * (c_in + c_out)

    db_out_sw0 = _out_db(X_SW_IN)
    db_out_sw1 = _out_db(X_SW_OUT)
    dt_sw = max(c_out - c_in, 1e-6)
    if (db_out_sw0 - db_out_sw1) / dt_sw > rate:
        db_out_sw1 = db_out_sw0 - rate * dt_sw
    x_sw_out = min(0.65, _x_from_out(db_out_sw1))
    db_out_sw1 = _out_db(x_sw_out)

    fade_rate = min(float(rate), HOLD_RATE)
    dt_to_hold = max(0.0, (db_out_sw1 - hold_db) / fade_rate)
    t_hold = c_out + dt_to_hold
    hold_end_db = hold_db - 1.0
    dt_exit = max(0.25, (hold_end_db - FLOOR) / rate)
    t_exit0 = e - dt_exit
    if t_exit0 <= t_hold + 0.5:
        t_hold = min(t_hold, e - dt_exit - 0.25)
        t_exit0 = max(t_hold + 0.25, e - dt_exit)

    x_hold_start = min(X_HOLD_MAX, _x_from_out(hold_db))
    x_hold_end = min(X_HOLD_MAX, _x_from_out(hold_end_db))
    x_floor_in = _x_from_in(FLOOR)

    db_in_sw0 = _in_db(X_SW_IN)
    t_rise0 = s + 0.25
    dt_pre = max(c_in - t_rise0, 1e-6)
    # Convex fade-in over [t_rise0, c_in] instead of jumping to -8 dB at bar 4 and stalling flat:
    # avoids exposing an early intro hook that vanishes in the pre-drop build dip before Drop 1.
    p_pre = min(PRE_EXP, max(1.0, 0.95 * RISE_CAP * 4.0 * dt_pre / max(db_in_sw0 - FLOOR, 1.0)))

    bars = set(float(b) for b in np.arange(s, e + 1e-9, STEP))
    for pt in (s, t_rise0, c_in, sw_c, c_out, t_hold, t_exit0, e):
        if s - 1e-9 <= pt <= e + 1e-9:
            bars.add(round(float(pt), 5))
    bars = sorted(bars)

    xs = []
    for b in bars:
        if b <= s + 1e-9:
            x = 0.0
        elif b <= t_rise0 + 1e-9:
            u = (b - s) / max(t_rise0 - s, 1e-9)
            x = u * x_floor_in
        elif b <= c_in + 1e-9:
            u = np.clip((b - t_rise0) / dt_pre, 0.0, 1.0)
            db_in = FLOOR + (u ** p_pre) * (db_in_sw0 - FLOOR)
            x = max(x_floor_in, min(X_SW_IN, _x_from_in(db_in)))
        elif b <= c_out + 1e-9:
            u = (b - c_in) / max(c_out - c_in, 1e-9)
            db_out = db_out_sw0 + u * (db_out_sw1 - db_out_sw0)
            x = _x_from_out(db_out)
        elif b <= t_hold + 1e-9:
            u = (b - c_out) / max(t_hold - c_out, 1e-9)
            db_out = db_out_sw1 + u * (hold_db - db_out_sw1)
            x = _x_from_out(db_out)
        elif b <= t_exit0 + 1e-9:
            u = (b - t_hold) / max(t_exit0 - t_hold, 1e-9)
            db_out = hold_db + u * (hold_end_db - hold_db)
            x = _x_from_out(db_out)
        elif b < e - 1e-9:
            u = (b - t_exit0) / max(e - t_exit0, 1e-9)
            db_out = hold_end_db + u * (FLOOR - hold_end_db)
            x = _x_from_out(db_out)
        else:
            x = 1.0
        xs.append([round(float(b), 5), round(float(np.clip(x, 0.0, 1.0)), 5)])

    for j in range(1, len(xs)):
        xs[j][1] = max(xs[j][1], xs[j - 1][1])
    xs[0][1] = 0.0
    xs[-1][1] = 1.0

    info = dict(
        k_drop=round(float(k_d), 2),
        c_out=round(float(c_out), 3),
        c_in=round(float(c_in), 3),
        sw_c=round(float(sw_c), 3),
        sw=float(sw_out),
        sw_in=float(sw_in),
        sw_out=float(sw_out),
        t_hold=round(float(t_hold), 3),
        t_exit0=round(float(t_exit0), 3),
        hold_db=float(hold_db),
        rate=float(rate),
        duration_bars=round(float(X), 2),
    )
    return xs, info


def apply_one(decks, trans, i, secs_of=None, hold_db=HOLD_DB, rate=RATE):
    t = trans[i]
    if not _eligible_blend(t, decks, i, secs_of):
        return None
    s, e = float(t['start_bar']), float(t['end_bar'])
    k_drop = _k_drop_in_blend(t, decks, i, secs_of)
    sw_in, sw_out = 2.0, 3.0
    xs, info = build_xfader(s, e, k_drop, hold_db=hold_db, rate=rate, sw_in=sw_in, sw_out=sw_out)

    t['xfader'] = xs
    t['fade'] = 'early_exit'
    t['swap_w'] = sw_out
    t['swap_bar'] = int(round(info['sw_c']))
    t['swap_ofs'] = float(info['sw_c'] - t['swap_bar'])
    t['swap_phrase'] = False
    t['bass_swap'] = [round(info['c_in'] - sw_in / 2.0, 3), round(info['c_out'] + sw_out / 2.0, 3)]
    t['tech'] = f"{int(round(e - s))}-bar early-exit breakdown blend + drop-anchored bass handoff + {hold_db:g} dB drop hold"
    if t.get('high_bar') is not None:
        xs_t = [p[0] for p in xs]
        xs_v = [p[1] for p in xs]
        hc = float(t['high_bar']) + 1.0
        x_hc = float(np.interp(hc, xs_t, xs_v))
        if hc > info['c_out'] or x_hc < 0.12 or x_hc > 0.88:
            new_hb = max(s + 1.0, info['c_in'] - 1.5)
            x_new = float(np.interp(new_hb + 1.0, xs_t, xs_v))
            if 0.12 <= x_new <= 0.88 and new_hb + 1.0 <= info['c_out']:
                t['high_bar'] = float(round(new_hb, 2))
            else:
                t['high_bar'] = None
    t['early_exit'] = info

    for idx in (i, i + 1):
        d = decks[idx]
        g = []
        if idx > 0:
            g += [[p[0], round(float(np.sin(p[1] * np.pi / 2.0)), 5)] for p in trans[idx - 1]['xfader']]
        if idx < len(decks) - 1:
            g += [[p[0], round(float(np.cos(p[1] * np.pi / 2.0)), 5)] for p in trans[idx]['xfader']]
        d['auto']['gain'] = g

        lo = []
        if idx > 0 and trans[idx - 1].get('swap_w', 0) > 0:
            pt = trans[idx - 1]
            if pt.get('early_exit'):
                lo += _ramp(pt['early_exit']['c_in'], True, pt['early_exit'].get('sw_in', 2.0))
            else:
                lo += [p for p in (d['auto'].get('low') or []) if p[0] <= pt['end_bar'] + 1.0]
        if idx < len(decks) - 1 and trans[idx].get('swap_w', 0) > 0:
            nt = trans[idx]
            if nt.get('early_exit'):
                lo += _ramp(nt['early_exit']['c_out'], False, nt['early_exit'].get('sw_out', 3.0))
            else:
                lo += [p for p in (d['auto'].get('low') or []) if p[0] >= nt['start_bar'] - 1.0]
        if lo:
            d['auto']['low'] = lo
        elif 'low' in d['auto'] and (idx == 0 or trans[idx - 1].get('swap_w', 0) == 0) and (idx == len(decks) - 1 or trans[idx].get('swap_w', 0) == 0):
            d['auto'].pop('low', None)

        hi = []
        if idx > 0 and trans[idx - 1].get('high_bar') is not None:
            hi += _ramp(trans[idx - 1]['high_bar'] + 1.0, True, 2.0)
        if idx < len(decks) - 1 and trans[idx].get('high_bar') is not None:
            hi += _ramp(trans[idx]['high_bar'] + 1.0, False, 2.0)
        if hi:
            d['auto']['high'] = hi
        else:
            d['auto'].pop('high', None)
    return info


def apply(decks, trans, secs_of=None, skip=()):
    if not flag_on():
        return []
    hold_db = float(os.environ.get('EARLY_EXIT_HOLD_DB', HOLD_DB))
    rate = float(os.environ.get('EARLY_EXIT_RATE', RATE))
    out = []
    for i, t in enumerate(trans):
        if t['a'] in skip:
            continue
        res = apply_one(decks, trans, i, secs_of=secs_of, hold_db=hold_db, rate=rate)
        if res is not None:
            out.append(dict(a=t['a'], b=t['b'], **res))
    return out


def predict_dips(hiA, loA, hiB, loB, wa, wb, ee_pts, ee_info):
    """Predict full-band V-dip (pred_vdip) and engine-induced low-band deficit (pred_ldip)
    over an early-exit blend window.

    hiA/hiB are >150 Hz band dB arrays (mix_simple.F()[0]); loA/loB are <150 Hz band dB arrays.
    Uses hi + attenuated_low directly (no double-subtraction of lo), and compares blend lows
    against the unattenuated active source low band (loA before c_in, max(loA, loB) from c_in)
    so Track A's own natural breakdown before the swap is not misread as an engine bass hole.
    """
    ps, pls, lo_ref = [], [], []
    cin = float(ee_info['c_in'])
    swi = float(ee_info.get('sw_in', 2.0))
    cout = float(ee_info['c_out'])
    swo = float(ee_info.get('sw_out', 3.0))
    for k, (xa, xb) in enumerate(zip(wa, wb)):
        t = k + 0.5
        x = float(np.interp(t, ee_pts[0], ee_pts[1]))
        ga, gb = np.cos(x * np.pi / 2.0), np.sin(x * np.pi / 2.0)
        la = float(np.clip((cout + swo / 2.0 - t) / max(swo, 1e-6), 0.0, 1.0))
        lb = float(np.clip((t - (cin - swi / 2.0)) / max(swi, 1e-6), 0.0, 1.0))
        loa = (la ** 2) * (10.0 ** (float(loA[xa]) / 10.0))
        lob = (lb ** 2) * (10.0 ** (float(loB[xb]) / 10.0))
        pa = max(10.0 ** (float(hiA[xa]) / 10.0) + loa, 1e-12)
        pb = max(10.0 ** (float(hiB[xb]) / 10.0) + lob, 1e-12)
        ps.append(10.0 * np.log10((ga ** 2) * pa + (gb ** 2) * pb))
        pls.append(10.0 * np.log10(max((ga ** 2) * loa + (gb ** 2) * lob, 1e-12)))
        lo_ref.append(float(loA[xa]) if t < cin else float(max(loA[xa], loB[xb])))
    pvd = round(max([min(max(ps[k - 2:k]), max(ps[k + 1:k + 3])) - ps[k] for k in range(2, len(ps) - 2)] + [0.0]), 2)
    pld = round(max([r - p for r, p in zip(lo_ref, pls)] + [0.0]), 2) if pls else 0.0
    return pvd, pld
