"""PRO_FADE=1 (2026-11-25, off by default): low-DOF learned pro fade shape.

5 parameters fit strictly on corpus_v2 dev pairs (no held-out test pairs):
  - entry_db       : incoming track initial entry level after smooth 0-click ramp (dB)
  - shelf_db       : outgoing track partial hold-shelf level after swap handoff (dB)
  - exit_slope     : outgoing track exit rate from shelf_db to FLOOR (dB/bar)
  - high_offset_db : >4 kHz high-band offset above main fader during blend (dB, capped at 0 dB)
  - bass_cut_db    : <150 Hz outgoing bass target during shelf (-40 = hard kill)
  - bass_rel_db    : (2026-11-26, 0 = off) after the bass handoff, the outgoing's leftover bass is
                     also held this many dB under the incoming's ACTUAL bass that bar (per-bar <150 Hz
                     levels of both source tracks x fader x low lane). Fixes the L1 mud found on dev:
                     a fixed partial cut (-24 dB) met bass-light incoming intros at equal level.
  - bass_sw        : (2026-11-26, 0 = keep the plan's swap width) max width in bars of both <150 Hz
                     handoff ramps. Pros swap bass with a quick EQ move; our 4-bar raised-cosine ramps
                     sit both basses at equal level for ~2 bars (summed lows +3 dB = L1).
  - bass_rel_mid   : (2026-11-26, 0 = off) start the bass_rel_db cap at the CENTRE of the outgoing
                     <150 Hz handoff ramp instead of its end. r4 dev diag: on sirenity__56 the
                     outgoing -24 dB residual met the bass-light incoming at equal level inside the
                     ramp tail (bar 17, -47.0 vs -47.8 dB), before the end-of-ramp cap could act.

Never touches defaults or rules.json when PRO_FADE is off.
"""
from __future__ import annotations
import os
import numpy as np
import tail_exit as TE

FLOOR = -24.0
RISE_CAP = 2.90   # dB / beat, strictly under X1's 3.0 cap
STEP = 1.0 / 16.0

# Initial defaults (pro median prior; updated ONLY after corpus_v2 dev fit)
DEFAULT_PARAMS = dict(
    entry_db=-10.0,
    shelf_db=-11.0,
    exit_slope=2.0,
    high_offset_db=6.5,
    bass_cut_db=-20.0,
    bass_rel_db=0.0,
    bass_sw=0.0,
    bass_rel_mid=0.0,
)


def flag_on(env=None):
    v = (env or os.environ).get('PRO_FADE', '0')
    return str(v).strip().lower() in ('1', 'true', 'yes', 'on')


def params_from_env(env=None):
    e = env or os.environ
    return dict(
        entry_db=float(e.get('PRO_FADE_ENTRY_DB', DEFAULT_PARAMS['entry_db'])),
        shelf_db=float(e.get('PRO_FADE_SHELF_DB', DEFAULT_PARAMS['shelf_db'])),
        exit_slope=float(e.get('PRO_FADE_EXIT_SLOPE', DEFAULT_PARAMS['exit_slope'])),
        high_offset_db=float(e.get('PRO_FADE_HIGH_OFS', DEFAULT_PARAMS['high_offset_db'])),
        bass_cut_db=float(e.get('PRO_FADE_BASS_CUT_DB', DEFAULT_PARAMS['bass_cut_db'])),
        bass_rel_db=float(e.get('PRO_FADE_BASS_REL', DEFAULT_PARAMS['bass_rel_db']) or 0.0),
        bass_sw=float(e.get('PRO_FADE_BASS_SW', DEFAULT_PARAMS['bass_sw']) or 0.0),
        bass_rel_mid=float(e.get('PRO_FADE_BASS_REL_MID', DEFAULT_PARAMS['bass_rel_mid']) or 0.0),
    )


def _in_db(x):
    return float(20.0 * np.log10(np.sin(np.clip(float(x), 0.0, 1.0) * np.pi / 2.0) + 1e-9))


def _out_db(x):
    return float(TE._db(x))


def _x_from_in(db):
    return float(2.0 / np.pi * np.arcsin(min(1.0, 10.0 ** (float(db) / 20.0))))


def _x_from_out(db):
    return float(TE._x(db))


def _ramp(c, up, w=2.0, g0=None, g1=None):
    if g0 is None:
        g0 = 0.0 if up else 1.0
    if g1 is None:
        g1 = 1.0 if up else 0.0
    pts = []
    for j in range(17):
        t01 = (1.0 - np.cos(np.pi * j / 16.0)) / 2.0
        val = float(g0) + (float(g1) - float(g0)) * t01
        pts.append([round(c - w / 2.0 + w * j / 16.0, 5), round(float(val), 5)])
    return pts


def build_xfader(s, e, c_in, c_out, entry_db=-10.0, shelf_db=-11.0, exit_slope=2.0, anchor_early=False):
    """Build monotonic X1-compliant xfader x(t) from the 3 fade-shape parameters."""
    s, e = float(s), float(e)
    X = max(4.0, e - s)
    entry_db = float(np.clip(-abs(float(entry_db)), -22.0, -4.0))
    shelf_db = float(np.clip(-abs(float(shelf_db)), -20.0, -5.0))
    exit_slope = float(np.clip(float(exit_slope), 1.0, 6.0))

    c_lo = max(s + 1.5, min(float(c_in), float(c_out)))
    c_hi = min(e - 2.0, max(float(c_in), float(c_out)))
    if not anchor_early and str(os.environ.get('PRO_FADE_PRO_ANCHOR', '1')).strip() != '0':
        # Standard blends swap bass early (SWAP_POS=0.21), whereas pro faders keep A near full
        # until ~35% into the blend and hand off to shelf by ~50% (leaving early_exit anchored to Drop 1).
        c_lo = max(c_lo, s + 0.32 * X)
        c_hi = min(e - 2.0, max(c_hi, s + 0.48 * X))
    if c_hi < c_lo + 0.5:
        c_hi = min(e - 1.5, c_lo + 0.5)

    # Smooth rise from FLOOR (-24 dB) to entry_db honoring <= RISE_CAP dB/beat
    max_rate_bar = 4.0 * 0.92 * RISE_CAP
    dt_floor_to_ent = max(0.25, (entry_db - FLOOR) / max_rate_bar)
    t_ent = min(c_lo - 0.5, s + 0.25 + dt_floor_to_ent)
    if t_ent <= s + 0.25:
        t_ent = s + 0.25
    x_floor_in = _x_from_in(FLOOR)
    x_ent = float(np.clip(_x_from_in(entry_db), x_floor_in + 0.01, 0.48))

    # By c_lo, incoming reaches at least ~ -5 dB (x ~ 0.36..0.46)
    x_sw_lo = float(np.clip(max(x_ent + 0.08, 0.38), x_ent + 0.02, 0.55))
    db_in_sw0 = _in_db(x_sw_lo)
    db_out_sw0 = _out_db(x_sw_lo)

    # Across [c_lo, c_hi], handoff incoming toward full / outgoing toward shelf
    max_sw_drop = max(1.5, min(exit_slope * 1.5, 3.5) * max(c_hi - c_lo, 0.5))
    db_out_sw1 = max(shelf_db + 1.0, min(db_out_sw0 - 1.5, db_out_sw0 - max_sw_drop * 0.6))
    x_sw_hi = float(np.clip(_x_from_out(db_out_sw1), x_sw_lo + 0.02, 0.78))
    db_out_sw1 = _out_db(x_sw_hi)

    # Hold shelf & final exit ramp at exit_slope (dB/bar)
    hold_end_db = shelf_db - 1.0
    dt_exit = max(0.5, (hold_end_db - FLOOR) / exit_slope)
    # Ensure exit slope also respects RISE_CAP per beat
    dt_exit = max(dt_exit, (hold_end_db - FLOOR) / max_rate_bar)
    t_exit0 = e - dt_exit

    dt_to_hold = max(0.25, (db_out_sw1 - shelf_db) / min(max(exit_slope, 1.5), 2.5))
    t_hold = c_hi + dt_to_hold
    if t_exit0 <= t_hold + 0.25:
        # Short blend: allocate half post-swap to reaching shelf, half to exiting
        avail = max(0.5, e - c_hi)
        t_hold = c_hi + 0.45 * avail
        t_exit0 = c_hi + 0.55 * avail

    bars = set(float(b) for b in np.arange(s, e + 1e-9, STEP))
    for pt in (s, s + 0.25, t_ent, c_lo, c_hi, t_hold, t_exit0, e):
        if s - 1e-9 <= pt <= e + 1e-9:
            bars.add(round(float(pt), 5))
    bars = sorted(bars)

    xs = []
    for b in bars:
        if b <= s + 1e-9:
            x = 0.0
        elif b <= s + 0.25 + 1e-9:
            u = (b - s) / 0.25
            x = u * x_floor_in
        elif b <= t_ent + 1e-9:
            u = (b - (s + 0.25)) / max(t_ent - (s + 0.25), 1e-9)
            db_in = FLOOR + u * (entry_db - FLOOR)
            x = max(x_floor_in, min(x_ent, _x_from_in(db_in)))
        elif b <= c_lo + 1e-9:
            u = (b - t_ent) / max(c_lo - t_ent, 1e-9)
            db_in = entry_db + u * (db_in_sw0 - entry_db)
            x = max(x_ent, min(x_sw_lo, _x_from_in(db_in)))
        elif b <= c_hi + 1e-9:
            u = (b - c_lo) / max(c_hi - c_lo, 1e-9)
            db_out = db_out_sw0 + u * (db_out_sw1 - db_out_sw0)
            x = _x_from_out(db_out)
        elif b <= t_hold + 1e-9:
            u = (b - c_hi) / max(t_hold - c_hi, 1e-9)
            db_out = db_out_sw1 + u * (shelf_db - db_out_sw1)
            x = _x_from_out(db_out)
        elif b <= t_exit0 + 1e-9:
            u = (b - t_hold) / max(t_exit0 - t_hold, 1e-9)
            db_out = shelf_db + u * (hold_end_db - shelf_db)
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
    return xs, dict(
        t_ent=round(float(t_ent), 3),
        c_lo=round(float(c_lo), 3),
        c_hi=round(float(c_hi), 3),
        t_hold=round(float(t_hold), 3),
        t_exit0=round(float(t_exit0), 3),
        entry_db=float(entry_db),
        shelf_db=float(shelf_db),
        exit_slope=float(exit_slope),
    )


def _high_lane_out(xs, high_offset_db):
    """Outgoing >4 kHz lane: rides high_offset_db hotter than fader gain (capped at 0 dB net),
    tapering cleanly back to unity at s and e."""
    if high_offset_db <= 0.1:
        return []
    s, e = xs[0][0], xs[-1][0]
    max_boost = 10.0 ** (float(high_offset_db) / 20.0)
    pts = []
    for b, x in xs:
        ga = max(float(np.cos(x * np.pi / 2.0)), 1e-4)
        # Smooth envelope: 0->1 over first 1 bar, 1->0 over last 2 bars before e
        w_in = float(np.clip((b - s) / 1.0, 0.0, 1.0))
        w_out = float(np.clip((e - b) / 2.0, 0.0, 1.0))
        env = min(w_in, w_out)
        target_boost = min(max_boost, 1.0 / ga)
        gh = 1.0 + env * (target_boost - 1.0)
        pts.append([round(float(b), 5), round(float(gh), 5)])
    return pts


def _high_lane_in(xs, c_in, high_offset_db):
    """Incoming >4 kHz lane: enters hot (up to high_offset_db over fader gain, capped at 0 dB net),
    converging to unity as fader reaches full."""
    if high_offset_db <= 0.1:
        return []
    s, e = xs[0][0], xs[-1][0]
    max_boost = 10.0 ** (float(high_offset_db) / 20.0)
    pts = []
    for b, x in xs:
        gb = max(float(np.sin(x * np.pi / 2.0)), 1e-4)
        w_start = float(np.clip((b - s) / 0.25, 0.0, 1.0))
        w_end = float(np.clip((e - b) / 1.0, 0.0, 1.0))
        target_boost = min(max_boost, 1.0 / gb)
        gh = 1.0 + min(w_start, w_end) * (target_boost - 1.0)
        pts.append([round(float(b), 5), round(float(gh), 5)])
    return pts


def _low_lane_out(c_out, sw_out, t_exit0, e, shelf_db, bass_cut_db):
    """Outgoing <150 Hz lane: hard kill if bass_cut_db <= -35, else partial cut during shelf -> 0 at exit."""
    if float(bass_cut_db) <= -35.0:
        return _ramp(c_out, False, sw_out, 1.0, 0.0)
    g_shelf = max(10.0 ** (float(shelf_db) / 20.0), 1e-4)
    g_bass_target = 10.0 ** (float(bass_cut_db) / 20.0)
    g_cut = float(np.clip(g_bass_target / g_shelf, 0.0, 0.95))
    pts = _ramp(c_out, False, sw_out, 1.0, g_cut)
    # Finish cutting g_cut -> 0.0 smoothly across [t_exit0, e]
    exit_c = 0.5 * (max(c_out + sw_out / 2.0 + 0.5, t_exit0) + e)
    exit_w = max(1.0, min(3.0, e - max(c_out + sw_out / 2.0 + 0.25, t_exit0)))
    if exit_c - exit_w / 2.0 <= pts[-1][0]:
        exit_c = pts[-1][0] + exit_w / 2.0 + 0.05
    pts += _ramp(min(e - exit_w / 2.0, exit_c), False, exit_w, g_cut, 0.0)
    return pts


def _lane_at(pts, b, default=1.0):
    if not pts:
        return default
    return float(np.interp(b, [p[0] for p in pts], [p[1] for p in pts], left=pts[0][1], right=pts[-1][1]))


def _src_low(deck, lows, b):
    """Source-track <150 Hz level (dB) under mix bar b for this deck, or None."""
    if lows is None:
        return None
    k = int(np.floor(float(b) - float(deck['start_bar'])))
    fm = deck.get('full_map') or []
    if not (0 <= k < len(fm)):
        return None
    sb = fm[k][0] if isinstance(fm[k], (list, tuple)) else fm[k]
    try:
        v = float(lows[int(sb)])
    except (TypeError, ValueError, IndexError):
        return None
    return v if np.isfinite(v) else None


def rel_cap_low_lane(lo_a, t, deck_a, deck_b, lows_a, lows_b, lo_b, rel_db, c_out, sw_out, step=0.25, from_mid=False):
    """Cap the outgoing low lane so A's net bass sits >= rel_db under B's net bass on every
    sub-bar after A's handoff ramp ends (c_out + sw_out/2) up to the blend end. Never raises the lane."""
    if rel_db <= 0 or not lo_a or lows_a is None or lows_b is None:
        return lo_a
    xs = t['xfader']
    b0 = float(c_out) + (0.0 if from_mid else float(sw_out) / 2.0)
    e = float(t['end_bar'])
    if b0 >= e:
        return lo_a
    grid = sorted(set([p[0] for p in lo_a if p[0] >= b0] + [round(float(b), 5) for b in np.arange(b0, e + 1e-9, step)]))
    capped = {}
    for b in grid:
        x = _lane_at(xs, b, 0.0)
        ga = max(float(np.cos(x * np.pi / 2.0)), 1e-6)
        gb = max(float(np.sin(x * np.pi / 2.0)), 1e-6)
        la, lb = _src_low(deck_a, lows_a, b), _src_low(deck_b, lows_b, b)
        cur = _lane_at(lo_a, b)
        if la is None or lb is None:
            capped[b] = cur
            continue
        b_net = lb + 20.0 * np.log10(gb * max(_lane_at(lo_b, b), 1e-6))
        a_full = la + 20.0 * np.log10(ga)
        cap = 10.0 ** ((b_net - float(rel_db) - a_full) / 20.0)
        capped[b] = float(min(cur, max(cap, 0.0)))
    # monotone: once cut, the outgoing bass never comes back (no 'appears, vanishes, returns' in the lows)
    vals = [capped[b] for b in grid]
    for j in range(1, len(vals)):
        vals[j] = min(vals[j], vals[j - 1])
    keep = [p for p in lo_a if p[0] < b0]
    out = keep + [[round(float(b), 5), round(float(min(v, _lane_at(lo_a, b))), 5)] for b, v in zip(grid, vals)]
    return out


def apply(decks, trans, params=None, skip=(), lows_of=None):
    """Reshape all active blends (both early_exit and standard) using the 5-DOF pro fade."""
    if params is None:
        if not flag_on():
            return []
        params = params_from_env()
    entry_db = float(params['entry_db'])
    shelf_db = float(params['shelf_db'])
    exit_slope = float(params['exit_slope'])
    high_offset_db = float(params['high_offset_db'])
    bass_cut_db = float(params['bass_cut_db'])
    bass_rel_db = float(params.get('bass_rel_db', 0.0) or 0.0)
    bass_sw = float(params.get('bass_sw', 0.0) or 0.0)
    bass_rel_mid = float(params.get('bass_rel_mid', 0.0) or 0.0) > 0
    _bw = (lambda w: min(float(w), bass_sw)) if bass_sw > 0 else (lambda w: float(w))
    rel_info = {}

    out = []
    for i, t in enumerate(trans):
        if t['a'] in skip:
            continue
        s, e = float(t['start_bar']), float(t['end_bar'])
        if e - s < 6.0:
            continue
        if t.get('early_exit'):
            ee = t['early_exit']
            c_in = float(ee['c_in'])
            c_out = float(ee['c_out'])
            sw_in = float(ee.get('sw_in', 2.0))
            sw_out = float(ee.get('sw_out', 3.0))
        else:
            sw = float(t.get('swap_w', 3.0) or 3.0)
            if sw > 0 and t.get('bass_swap'):
                lo0, lo1 = float(t['bass_swap'][0]), float(t['bass_swap'][1])
                c_out = lo0 + sw / 2.0
                c_in = lo1 - sw / 2.0
                sw_in = sw
                sw_out = sw
            else:
                c_sw = float(t.get('swap_bar', (s + e) / 2.0))
                c_in = c_sw
                c_out = c_sw
                sw_in = max(2.0, sw)
                sw_out = max(2.0, sw)
            # Ensure swap centers sit comfortably inside [s+1.5, e-3.0]
            c_in = float(np.clip(c_in, s + 1.5, e - 3.0))
            c_out = float(np.clip(c_out, s + 1.5, e - 2.5))

        # 2026-11-26: respect an earlier exit already chosen upstream (tail_exit runs before us). Without this the
        # pro fade re-stretched A to end_bar and held it on the shelf, undoing ee_r7's early exit on pola02
        # (A audible bars 128-143) and burying B's quiet intro under A (incoming_vanish 6.9 dB > p95).
        e_fade = e
        te = t.get('tail_exit') or {}
        if str(os.environ.get('PRO_FADE_RESPECT_EXIT', '1')).strip() != '0' and te.get('exit_bar') is not None:
            xb = float(te['exit_bar'])
            if s + 6.0 <= xb < e - 0.5:
                e_fade = xb
                c_in = float(np.clip(c_in, s + 1.5, e_fade - 3.0))
                c_out = float(np.clip(c_out, s + 1.5, e_fade - 2.5))
        xs, info = build_xfader(s, e_fade, c_in, c_out, entry_db=entry_db, shelf_db=shelf_db, exit_slope=exit_slope, anchor_early=bool(t.get('early_exit')))
        if e_fade < e:
            xs.append([round(float(e), 5), 1.0])
            info['exit_bar'] = round(float(e_fade), 3)
        t['xfader'] = xs
        t['pro_fade'] = dict(params=dict(params), info=info)
        if 'pro-learned fade' not in t.get('tech', ''):
            t['tech'] = t.get('tech', '') + ' + pro-learned fade'
        out.append(dict(a=t['a'], b=t['b'], **info))

        # Rebuild gain, low, high lanes cleanly for decks i and i+1
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
                if pt.get('pro_fade'):
                    pc_in = float(pt['early_exit']['c_in']) if pt.get('early_exit') else (
                        float(pt['bass_swap'][1]) - float(pt['swap_w']) / 2.0 if pt.get('bass_swap') else float(pt['swap_bar'])
                    )
                    psw_in = _bw(float(pt['early_exit'].get('sw_in', 2.0)) if pt.get('early_exit') else float(pt['swap_w']))
                    lo += _ramp(float(np.clip(pc_in, pt['start_bar'] + 1.5, pt['end_bar'] - 2.5)), True, psw_in, 0.0, 1.0)
                else:
                    lo += [p for p in (d['auto'].get('low') or []) if p[0] <= pt['end_bar'] + 1.0]
            if idx < len(decks) - 1 and trans[idx].get('swap_w', 0) > 0:
                nt = trans[idx]
                if nt.get('pro_fade'):
                    nc_out = float(nt['early_exit']['c_out']) if nt.get('early_exit') else (
                        float(nt['bass_swap'][0]) + float(nt['swap_w']) / 2.0 if nt.get('bass_swap') else float(nt['swap_bar'])
                    )
                    nsw_out = _bw(float(nt['early_exit'].get('sw_out', 3.0)) if nt.get('early_exit') else float(nt['swap_w']))
                    nc_out = float(np.clip(nc_out, nt['start_bar'] + 1.5, nt['end_bar'] - 2.5))
                    lo_out = _low_lane_out(nc_out, nsw_out, nt['pro_fade']['info']['t_exit0'], float(nt['pro_fade']['info'].get('exit_bar', nt['end_bar'])), shelf_db, bass_cut_db)
                    if bass_rel_db > 0 and lows_of is not None:
                        nb = decks[idx + 1]
                        nb_in = float(nt['early_exit']['c_in']) if nt.get('early_exit') else (
                            float(nt['bass_swap'][1]) - float(nt['swap_w']) / 2.0 if nt.get('bass_swap') else float(nt['swap_bar']))
                        nb_sw = _bw(float(nt['early_exit'].get('sw_in', 2.0)) if nt.get('early_exit') else float(nt['swap_w']))
                        lo_b = _ramp(float(np.clip(nb_in, nt['start_bar'] + 1.5, nt['end_bar'] - 2.5)), True, nb_sw, 0.0, 1.0)
                        try:
                            la_, lb_ = lows_of(d['id']), lows_of(nb['id'])
                        except Exception:
                            la_, lb_ = None, None
                        n0 = len(lo_out)
                        lo_out = rel_cap_low_lane(lo_out, nt, d, nb, la_, lb_, lo_b, bass_rel_db, nc_out, nsw_out, from_mid=bass_rel_mid)
                        rel_info[idx] = n0 != len(lo_out) or la_ is not None
                    lo += lo_out
                else:
                    lo += [p for p in (d['auto'].get('low') or []) if p[0] >= nt['start_bar'] - 1.0]
            if lo:
                d['auto']['low'] = lo

            hi = []
            if idx > 0 and trans[idx - 1].get('pro_fade'):
                pt = trans[idx - 1]
                pc_in = float(pt['early_exit']['c_in']) if pt.get('early_exit') else float(pt.get('swap_bar', pt['start_bar'] + 3))
                hi += _high_lane_in(pt['xfader'], pc_in, high_offset_db)
            if idx < len(decks) - 1 and trans[idx].get('pro_fade'):
                nt = trans[idx]
                hi += _high_lane_out(nt['xfader'], high_offset_db)
            if hi:
                d['auto']['high'] = hi
            else:
                d['auto'].pop('high', None)
    for i, t in enumerate(trans):
        if t.get('pro_fade') and i in rel_info:
            t['pro_fade']['info']['bass_rel_db'] = bass_rel_db
    return out
