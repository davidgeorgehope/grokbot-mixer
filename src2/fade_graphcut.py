"""FADE=graphcut: per-band time-frequency handover (Robinson & Brown, ISMIR 2019 LBD,
https://arxiv.org/abs/2301.13380), off by default.

In the blend window a min-cut is taken over a bar-quantized time x 6-band grid
(20-80, 80-250, 250-800, 800-2500, 2500-7000, 7000-20000 Hz). Edge costs follow
the paper's |A-B| seam term, plus Banger 6-band clash and a Manabe-style
collision/continuity term from spectral_score.py. Clashing bands get a short
bar-centred swap; compatible mid/high bands may overlap. Bass (<250 Hz) is a
hard seam: never doubles, and a cut that would open a bass-gap (>GAP_DB 9.84)
is forbidden when a legal alternative exists. The bass and high seams are
emitted as the existing 'low'/'high' auto lanes so X1 still holds (bass 1-4
bars at x 0.2-0.65, high 1-2 bars at x 0.1-0.9). Mid seams live on
d['graphcut'] and are applied by the engine instead of the master fader.

Planning still uses the FADE=long shape (current protrans default). This module
does not read or write protrans/rules.json and does not change any threshold.
"""
from __future__ import annotations
import copy
import os
import numpy as np

import spectral_score as SS
import bassgap

BANDS = list(SS.BANDS_6)
EDGES = np.array(SS.BAND_EDGES_6, float)
BASS_IDX = (0, 1)          # <250 Hz
HIGH_IDX = (4, 5)          # >2500 Hz (engine HIGH_XO is 2000)
MID_IDX = (2, 3)
GAP_DB = float(bassgap.GAP_DB)  # 9.84, pro p95; used as a hard cut forbid, not loosened
INF = 1e9
CLASH_W = 12.0
COL_W = 2.0
CTY_W = 1.0
GAP_LATE_W = 30.0  # when every legal bass cut would gap, prefer the latest legal bar
SMOOTH_W = 3.0
BASS_COUPLE = 50.0
HIGH_COUPLE = 50.0
LEGAL_BASS_X = (0.2, 0.65)
LEGAL_HIGH_X = (0.1, 0.9)
BASS_W_MAX = 4.0
HIGH_W_MAX = 2.0
COMPAT_W = 8.0
CLASH_W_BARS = 2.0


def _db(e, eps=SS.EPS):
    return 10.0 * np.log10(np.maximum(np.asarray(e, float), eps))


def band_clash(eA, eB, floor_db=-40.0, rel_db=20.0):
    """Per-bar, per-band Banger-style fill clash (both decks fill the band).

    A deck only 'fills' a band when it is within rel_db of the louder of the
    two decks in that band (not just of its own window peak). Otherwise a
    quiet intro whose own peak is already a hole would look like a clash
    and pull the bass seam early (Final Hours -> Listen, 2026-11-13).
    """
    eA = np.asarray(eA, float)
    eB = np.asarray(eB, float)
    peak = max(float(eA.max()), float(eB.max()), SS.EPS)
    abs_floor = peak * 10 ** (floor_db / 10.0)
    joint = np.maximum(eA.max(axis=0), eB.max(axis=0)) + SS.EPS
    rel = joint * 10 ** (-rel_db / 10.0)
    fill_a = (eA >= abs_floor) & (eA >= rel)
    fill_b = (eB >= abs_floor) & (eB >= rel)
    return fill_a & fill_b


def occupancy(eA, eB, eps=SS.EPS):
    s = np.asarray(eA, float) + np.asarray(eB, float) + eps
    return np.asarray(eA, float) / s, np.asarray(eB, float) / s


def collision_term(eA, eB):
    """Manabe-like per-bar collision: both decks occupy the band with energy."""
    rA, rB = occupancy(eA, eB)
    qA = np.asarray(eA, float) / (np.maximum(np.max(eA, axis=0, keepdims=True), SS.EPS))
    qB = np.asarray(eB, float) / (np.maximum(np.max(eB, axis=0, keepdims=True), SS.EPS))
    return np.clip(rA * rB * qA * qB, 0.0, 1.0)


def time_costs(dbA, dbB, clash, col, xfade, bass_idx=BASS_IDX, high_idx=HIGH_IDX,
               legal_bass=LEGAL_BASS_X, legal_high=LEGAL_HIGH_X, gap_db=GAP_DB):
    """(T-1, B) n-link capacities. Lower = preferred cut. Paper term is |A-B|.

    Clash/collision make a cut cheaper (get out of the double). A bass-gap or
    an X1-illegal centre is forbidden (INF) when a legal alternative exists.
    """
    T, B = dbA.shape
    C = np.zeros((T - 1, B), float)
    forbid_gap = np.zeros((T - 1, B), bool)
    forbid_win = np.zeros((T - 1, B), bool)
    xf = np.asarray(xfade, float)
    # Bass coverage is judged on the summed <250 Hz energy, not each sub-band
    # alone (80-250 can look "covered" while 20-80 is a hole, and the release
    # dip is measured on a single <150 Hz mixdown).
    bass_idx = tuple(bass_idx)
    if bass_idx:
        eA_s = np.sum(10 ** (dbA[:, list(bass_idx)] / 10.0), axis=1)
        eB_s = np.sum(10 ** (dbB[:, list(bass_idx)] / 10.0), axis=1)
        dbA_s, dbB_s = _db(eA_s), _db(eB_s)
        bodyA = float(np.median(dbA_s))
    else:
        dbA_s = dbB_s = None
        bodyA = 0.0
    for t in range(T - 1):
        xmid = 0.5 * (xf[t] + xf[t + 1]) if t + 1 < len(xf) else float(xf[min(t, len(xf) - 1)])
        for b in range(B):
            sim = abs(dbA[t, b] - dbB[t, b]) + abs(dbA[t + 1, b] - dbB[t + 1, b])
            cl = 0.5 * (float(clash[t, b]) + float(clash[min(t + 1, T - 1), b]))
            co = 0.5 * (float(col[t, b]) + float(col[min(t + 1, T - 1), b]))
            # continuity: don't drop the played energy at the join
            played_before = dbA[t, b]
            played_after = dbB[t + 1, b]
            cty = max(0.0, played_before - played_after)
            c = sim + CLASH_W * (1.0 - cl) + COL_W * (1.0 - co) + CTY_W * cty
            if b in bass_idx:
                drop = float(dbA_s[t] - dbB_s[t + 1])
                cover = float(bodyA - dbB_s[t + 1])
                if drop > 0:
                    c += 10.0 * drop
                # GAP_DB/2 is the existing bassgap.src_dip 'source is thin' threshold.
                # A single bar 8-9 dB under the outgoing body must not be treated
                # as the only 'legal' cover and force an early swap.
                if cover > gap_db / 2.0:
                    forbid_gap[t, b] = True
                    c += GAP_LATE_W * (T - 1 - t)
                if not (legal_bass[0] <= xmid <= legal_bass[1]):
                    forbid_win[t, b] = True
            if b in high_idx and not (legal_high[0] <= xmid <= legal_high[1]):
                forbid_win[t, b] = True
            C[t, b] = max(float(c), 1e-6)
    C, forbid = _relax_forbids(C, forbid_gap, forbid_win)
    C = np.where(forbid, INF, C)
    return C, forbid


def _relax_forbids(C, forbid_gap, forbid_win):
    """X1 window forbids always stay. Gap forbids stay when a legal non-gap
    cut exists; otherwise the soft continuity cost has to choose among legal bars.
    Never open an X1-illegal bass/high cut just to dodge a gap — the ramp is
    clamped into the legal window anyway."""
    forbid = forbid_win.copy()
    B = forbid.shape[1]
    for b in range(B):
        legal = ~forbid_win[:, b]
        if legal.any() and np.any((~forbid_gap[:, b]) & legal):
            forbid[:, b] = forbid_win[:, b] | forbid_gap[:, b]
        else:
            forbid[:, b] = forbid_win[:, b]
    return C, forbid


def freq_costs(dbA, dbB, T, B):
    """(T, B-1) n-link capacities between adjacent bands at the same bar."""
    F = np.zeros((T, B - 1), float)
    for t in range(T):
        for b in range(B - 1):
            sim = abs(dbA[t, b] - dbB[t, b]) + abs(dbA[t, b + 1] - dbB[t, b + 1])
            couple = 0.0
            if b == 0:
                couple = BASS_COUPLE
            if b == 4:
                couple = HIGH_COUPLE
            F[t, b] = max(SMOOTH_W * sim + couple, 1e-6)
    return F


def min_cut_seams(time_cost, freq_cost):
    """Monotonic min-cut on a T x B grid. Returns the first sink-bar per band (1..T-1).

    Source-set = still the outgoing track (A). Infinite edges pin bar 0 to A,
    the last bar to B, and forbid going back from B to A (Robinson & Brown /
    Kwatra graph-cut textures, with a directed monotonicity constraint).
    Forward time n-links carry the cut cost; backward time n-links are INF
    so a band cannot return to A after switching to B.
    """
    import networkx as nx
    Tm1, B = time_cost.shape
    T = Tm1 + 1
    G = nx.DiGraph()
    S, Tgt = 's', 't'

    def nid(t, b):
        return (int(t), int(b))

    for b in range(B):
        G.add_edge(S, nid(0, b), capacity=INF)
        G.add_edge(nid(T - 1, b), Tgt, capacity=INF)
        for t in range(T - 1):
            cap = float(time_cost[t, b])
            G.add_edge(nid(t, b), nid(t + 1, b), capacity=cap)
            G.add_edge(nid(t + 1, b), nid(t, b), capacity=INF)
    for t in range(T):
        for b in range(B - 1):
            cap = float(freq_cost[t, b])
            G.add_edge(nid(t, b), nid(t, b + 1), capacity=cap)
            G.add_edge(nid(t, b + 1), nid(t, b), capacity=cap)
    _value, (reach, _non) = nx.minimum_cut(G, S, Tgt)
    seams = np.full(B, T - 1, int)
    for b in range(B):
        for t in range(T):
            if nid(t, b) not in reach:
                seams[b] = t
                break
    return seams, float(_value)


def raise_cos_ramp(center, width, up, steps=16):
    """[[bar, gain], ...] raised-cosine, outgoing 1->0 / incoming 0->1, width bars."""
    w = max(float(width), 1e-9)
    c0 = float(center) - w / 2.0
    out = []
    for j in range(int(steps) + 1):
        u = j / steps
        g = (1 - np.cos(np.pi * u)) / 2 if up else (1 + np.cos(np.pi * u)) / 2
        out.append([round(c0 + w * u, 5), round(float(g), 5)])
    return out


def overlap_width(clash_frac, is_bass, is_high):
    if is_bass:
        return min(BASS_W_MAX, max(1.0, float(os.environ.get('BASS_SWAP_BARS', 3))))
    if is_high:
        return HIGH_W_MAX
    if clash_frac >= 0.5:
        return CLASH_W_BARS
    return COMPAT_W


def clamp_centre(centre, start, end, width, x_of, legal):
    """Slide a swap centre so it stays inside the blend and the X1 x-window."""
    lo_bar = start + width / 2
    hi_bar = end - width / 2
    c = float(np.clip(centre, lo_bar, hi_bar))
    if x_of is None or legal is None:
        return c
    # walk in 1/4-bar steps toward the legal window if needed
    xs = np.arange(lo_bar, hi_bar + 1e-9, 0.25)
    if len(xs) == 0:
        return c
    xv = np.array([float(x_of(x)) for x in xs])
    ok = (xv >= legal[0]) & (xv <= legal[1])
    if not ok.any():
        return c
    return float(xs[np.argmin(np.where(ok, np.abs(xs - c), np.inf))])


def curves_from_seams(seams, start, end, clash_frac, x_of=None, lead=(1.0, 0.0)):
    """Per-band gain curves for one blend, plus X1-legal low/high summaries."""
    X = end - start
    bands = []
    for b, seam in enumerate(seams):
        is_bass = b in BASS_IDX
        is_high = b in HIGH_IDX
        w = overlap_width(float(clash_frac[b]), is_bass, is_high)
        legal = LEGAL_BASS_X if is_bass else (LEGAL_HIGH_X if is_high else None)
        # seam is the first B bar (0-based in the window)
        centre = start + float(seam)
        if is_bass:
            centre = centre + 0.5 * (lead[1] - lead[0])
        centre = clamp_centre(centre, start, end, w, x_of, legal)
        # bass lead: outgoing starts earlier (same as fade_long)
        out_c = centre - (lead[0] if is_bass else 0.0)
        in_c = centre + (lead[1] if is_bass else 0.0)
        if is_bass:
            out_c = clamp_centre(out_c, start, end, w, x_of, legal)
            in_c = clamp_centre(in_c, start, end, w, x_of, legal)
        bands.append(dict(band=b, edges=(float(EDGES[b]), float(EDGES[b + 1])),
                          seam=int(seam), centre=float(centre), width=float(w),
                          clash=float(clash_frac[b]),
                          out=raise_cos_ramp(out_c, w, False),
                          inn=raise_cos_ramp(in_c, w, True)))
    # one low lane from the two bass bands (coupled; use mean centre)
    bass = [bands[i] for i in BASS_IDX]
    high = [bands[i] for i in HIGH_IDX]
    def _mean_lane(group, up):
        # identical if coupled; otherwise average the centre / max width, still legal
        w = max(g['width'] for g in group)
        if group is bass:
            w = min(BASS_W_MAX, max(1.0, w))
        elif group is high:
            w = min(HIGH_W_MAX, max(1.0, w))
        c = float(np.mean([g['centre'] for g in group]))
        legal = LEGAL_BASS_X if group is bass else LEGAL_HIGH_X
        c = clamp_centre(c, start, end, w, x_of, legal)
        if group is bass:
            c_out = clamp_centre(c - lead[0], start, end, w, x_of, legal)
            c_in = clamp_centre(c + lead[1], start, end, w, x_of, legal)
            return (raise_cos_ramp(c_out, w, False), raise_cos_ramp(c_in, w, True),
                    [round(c - lead[0] - w / 2, 3), round(c + lead[1] + w / 2, 3)], c, w)
        return (raise_cos_ramp(c, w, False), raise_cos_ramp(c, w, True),
                [round(c - w / 2, 3), round(c + w / 2, 3)], c, w)
    low_out, low_in, bass_swap, bass_c, bass_w = _mean_lane(bass, False)
    hi_out, hi_in, high_swap, high_c, high_w = _mean_lane(high, False)
    # force bass bands to share the emitted low lane (never-doubles + X1)
    for i in BASS_IDX:
        bands[i]['out'], bands[i]['inn'] = low_out, low_in
        bands[i]['width'] = bass_w
        bands[i]['centre'] = bass_c
    for i in HIGH_IDX:
        bands[i]['out'], bands[i]['inn'] = hi_out, hi_in
        bands[i]['width'] = high_w
        bands[i]['centre'] = high_c
    return dict(bands=bands, low=(low_out, low_in), high=(hi_out, hi_in),
                bass_swap=bass_swap, high_swap=high_swap,
                bass_centre=bass_c, high_centre=high_c, X=X)


def _xfader_interp(xs, bars):
    return np.interp(bars, [p[0] for p in xs], [p[1] for p in xs])


def _bar_energy(y, sr, bar_s, n_bars, t0=0.0):
    """(n_bars, 6) energy from a mono or stereo clip starting at mix-time t0."""
    mono = np.asarray(y, float)
    if mono.ndim == 2:
        mono = mono.mean(1)
    a = SS.analysis(mono, sr=sr, edges=EDGES)
    E = np.zeros((n_bars, 6), float)
    for k in range(n_bars):
        m = (a['times'] >= k * bar_s) & (a['times'] < (k + 1) * bar_s)
        if m.any():
            E[k] = a['energy'][m].mean(0)
    return E



def incoming_covers_bass(eA, eB, gap_db=GAP_DB):
    """True if incoming summed <250 Hz reaches the outgoing groove somewhere.

    Threshold is GAP_DB/2, the same 'source is thin' margin bassgap.src_dip uses.
    If this is False, a hard bass swap would hand the mix to a hole.
    """
    eA = np.asarray(eA, float)
    eB = np.asarray(eB, float)
    sA = np.sum(eA[:, list(BASS_IDX)], axis=1)
    sB = np.sum(eB[:, list(BASS_IDX)], axis=1)
    bodyA = float(np.median(_db(sA)))
    return bool(np.any(_db(sB) >= bodyA - gap_db / 2.0))


def xfader_bass_curves(xfader, start, end):
    """Outgoing bass follows the equal-power xfader; incoming bass follows the same equal-power xfader.

    Used when a hard 1-4 bar swap would open a hole. These curves are applied
    only through d['graphcut']['gains'], not auto['low']: a 16-bar decline
    would fail X1's 1-4 bar cap. Incoming source is thin so this does not double.
    """
    out, inn = [], []
    for p in xfader:
        if p[0] < start - 1e-6 or p[0] > end + 1e-6:
            continue
        x = float(p[1])
        out.append([float(p[0]), round(float(np.cos(x * np.pi / 2)), 5)])
        # Incoming must reach 1 by the window end so the post-blend / drop still
        # has bass (a constant 0 was left in place by np.interp and muted Listen
        # after Final Hours -> Listen, crashing the pro-aligner to score 12.55).
        inn.append([float(p[0]), round(float(np.sin(x * np.pi / 2)), 5)])
    return out, inn


def plan_seams(eA, eB, start, end, xfader, lead=(1.0, 0.0)):
    """From per-bar 6-band energies, return seams + curves for one blend."""
    eA = np.asarray(eA, float)
    eB = np.asarray(eB, float)
    T = min(len(eA), len(eB))
    eA, eB = eA[:T], eB[:T]
    dbA, dbB = _db(eA), _db(eB)
    clash = band_clash(eA, eB)
    col = collision_term(eA, eB)
    bars = start + np.arange(T)
    xf = _xfader_interp(xfader, bars)
    tc, _forb = time_costs(dbA, dbB, clash, col, xf)
    fc = freq_costs(dbA, dbB, T, eA.shape[1])
    seams, value = min_cut_seams(tc, fc)
    clash_frac = clash.mean(axis=0)
    packed = curves_from_seams(seams, start, end, clash_frac,
                               x_of=lambda bar: float(np.interp(bar, [p[0] for p in xfader],
                                                                [p[1] for p in xfader])),
                               lead=lead)
    packed['seams'] = seams.tolist()
    packed['cut_value'] = value
    packed['clash_frac'] = clash_frac.tolist()
    packed['clash'] = clash.astype(int).tolist()
    covers = incoming_covers_bass(eA, eB)
    packed['incoming_covers_bass'] = covers
    packed['bass_follow_fader'] = (not covers)
    if not covers:
        # Hard swap would dump the only bass in the mix (Final Hours -> Listen).
        out, inn = xfader_bass_curves(xfader, start, end)
        packed['low'] = (out, inn)
        packed['bass_swap'] = None
        for i in BASS_IDX:
            packed['bands'][i]['out'] = out
            packed['bands'][i]['inn'] = inn
            packed['bands'][i]['width'] = float(end - start)
            packed['bands'][i]['follow_fader'] = True
    return packed


def _slice_deck(y, deck, start, end, bs):
    i0 = int(round((start - deck['start_bar']) * bs))
    i1 = int(round((end - deck['start_bar']) * bs))
    i0 = max(0, i0)
    i1 = min(len(y), i1)
    return y[i0:i1]


def _dry(deck):
    import engine
    dd = copy.deepcopy(deck)
    dd['auto'] = {}
    dd.pop('graphcut', None)
    dd.pop('echo_out', None)
    return engine.render_deck(dd)


def apply(decks, trans, bar_s=None, sr=None):
    """Rewrite low/high lanes and attach d['graphcut'] for every blend. In-place."""
    import engine
    import fade_long as FL
    bar_s = float(bar_s or engine.BAR)
    sr = int(sr or engine.SR)
    bs = bar_s * sr
    blead = float(os.environ.get('BASS_LEAD', 1))
    for i, t in enumerate(trans):
        A, B = decks[i], decks[i + 1]
        s, e = float(t['start_bar']), float(t['end_bar'])
        X = e - s
        if X < 2:
            continue
        lead = FL.bass_lead(blead, phrase=bool(t.get('swap_phrase')), fade='long')
        ya, yb = _dry(A), _dry(B)
        pa = _slice_deck(ya, A, s, e, bs)
        pb = _slice_deck(yb, B, s, e, bs)
        n_bars = int(round(X))
        if len(pa) < 0.5 * n_bars * bs or len(pb) < 0.5 * n_bars * bs:
            continue
        eA = _bar_energy(pa, sr, bar_s, n_bars)
        eB = _bar_energy(pb, sr, bar_s, n_bars)
        packed = plan_seams(eA, eB, s, e, t['xfader'], lead=lead)
        t['graphcut'] = dict(seams=packed['seams'], cut_value=packed['cut_value'],
                             clash_frac=packed['clash_frac'],
                             bass_centre=packed['bass_centre'],
                             high_centre=packed['high_centre'],
                             incoming_covers_bass=packed.get('incoming_covers_bass', True),
                             bass_follow_fader=packed.get('bass_follow_fader', False),
                             bands=[{k: v[k] for k in ('band', 'edges', 'seam', 'centre', 'width', 'clash')}
                                    for v in packed['bands']])
        t['fade'] = 'graphcut'
        if packed.get('bass_follow_fader'):
            t['tech'] = (f"{int(X)}-bar graph-cut crossfade (Robinson & Brown, 6 bands;"
                         f" bass rides the fader, incoming has no low end)")
            t['bass_swap'] = None
            t['swap_bar'] = int(round((s + e) / 2))
            t['swap_ofs'] = 0.0
            t['swap_w'] = 0.0
        else:
            t['tech'] = (f"{int(X)}-bar graph-cut crossfade (Robinson & Brown, 6 bands)"
                         f" + {packed['low'][0][-1][0] - packed['low'][0][0][0]:g}-bar bass handoff")
            t['bass_swap'] = packed['bass_swap']
            t['swap_bar'] = int(round(packed['bass_centre']))
            t['swap_ofs'] = 0.0
            t['swap_w'] = float(packed['bands'][0]['width'])
        t['high_bar'] = int(round(packed['high_centre'] - 1))  # engine/high_at: ramp starts at high_bar+1
        # attach / replace lanes on each deck
        def _put(deck, incoming):
            lo = packed['low'][1 if incoming else 0]
            hi = packed['high'][1 if incoming else 0]
            auto = deck.setdefault('auto', {})
            # keep existing points from the other blend, replace this blend's
            # When bass rides the fader, do not write auto['low'] (X1 1-4 bar cap).
            if packed.get('bass_follow_fader'):
                auto['low'] = _splice_lane(auto.get('low') or [], [], s, e)
            else:
                auto['low'] = _splice_lane(auto.get('low') or [], lo, s, e)
            auto['high'] = _splice_lane(auto.get('high') or [], hi, s, e)
            gc = deck.setdefault('graphcut', dict(edges=EDGES.tolist(), gains=[[] for _ in range(6)]))
            gc['edges'] = EDGES.tolist()
            if len(gc['gains']) != 6:
                gc['gains'] = [[] for _ in range(6)]
            for b, band in enumerate(packed['bands']):
                lane = band['inn'] if incoming else band['out']
                gc['gains'][b] = _splice_lane(gc['gains'][b], lane, s, e)
        _put(A, False)
        _put(B, True)
    return decks, trans


def _splice_lane(old, new, s, e):
    """Keep points outside [s, e], insert new points for this blend."""
    kept = [p for p in (old or []) if p[0] < s - 1e-6 or p[0] > e + 1e-6]
    return sorted(kept + list(new), key=lambda p: p[0])


def render_bands(y, gc, start_bar, n, bs, sr):
    """Apply per-band gain curves to y (n, 2) via an STFT filter bank. Perfect
    reconstruction when every gain is 1 (up to STFT boundary error)."""
    from scipy.signal import stft, istft
    edges = np.array(gc.get('edges') or EDGES, float)
    gains = gc.get('gains') or []
    if not gains or all(not g for g in gains):
        return y
    t = np.arange(n) / bs + start_bar
    gl = []
    for g in gains:
        if not g:
            gl.append(np.ones(n, np.float32))
        else:
            gl.append(np.interp(t, [p[0] for p in g], [p[1] for p in g]).astype(np.float32))
    # skip the STFT if every band is unity
    if all(float(np.abs(g - 1).max()) < 1e-6 for g in gl):
        return y
    n_fft, hop = SS.N_FFT, SS.HOP
    out = np.zeros_like(y)
    for ch in range(y.shape[1]):
        x = np.ascontiguousarray(y[:, ch], float)
        freqs, times, Z = stft(x, fs=sr, window='hann', nperseg=n_fft,
                               noverlap=n_fft - hop, boundary='zeros', padded=True)
        # times are in seconds from the start of this deck clip
        mix_t = times / (bs / sr) + start_bar if bs else times
        # gain per frame per band, then map bins
        frame_g = np.ones((Z.shape[0], Z.shape[1]), float)
        for b, (lo, hi) in enumerate(zip(edges[:-1], edges[1:])):
            if b >= len(gl):
                break
            # first band includes DC / <20 Hz, last band includes Nyquist
            if b == 0:
                m = freqs < hi
            elif b == len(edges) - 2:
                m = freqs >= lo
            else:
                m = (freqs >= lo) & (freqs < hi)
            if not m.any():
                continue
            gf = np.interp(mix_t, t, gl[b])
            frame_g[m, :] *= gf
        _, xrec = istft(Z * frame_g, fs=sr, window='hann', nperseg=n_fft,
                         noverlap=n_fft - hop, input_onesided=True,
                         boundary=True)
        xrec = np.asarray(xrec, np.float32)
        if len(xrec) < n:
            xrec = np.pad(xrec, (0, n - len(xrec)))
        out[:, ch] = xrec[:n]
    return out


if __name__ == '__main__':
    print('fade_graphcut: import and call apply(decks, trans) or plan_seams(...)')
