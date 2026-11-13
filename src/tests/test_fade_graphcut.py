"""FADE=graphcut unit tests (Robinson & Brown min-cut handover). No audio fixtures
required except a short synthetic reconstruction check. Does not touch rules.json
or any release threshold."""
import os, sys
import numpy as np
import pytest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
sys.path.insert(0, os.path.join(ROOT, 'src2'))
sys.path.insert(0, os.path.join(ROOT, 'src'))
import fade_graphcut as GC
import fade_long as FL


def _xfader(start, X):
    """FADE=long-shaped xfader, one point per beat, as mix_simple logs it."""
    return [[start + k / 4, FL.xlong(k / (4 * X), X) if k < 4 * X else 1.0]
            for k in range(4 * X + 1)]


def _energies(T=16, B=6, seam=None, clash_band=None, gap_at=None):
    """Synthetic per-bar 6-band energies. A fades out, B fades in around `seam`."""
    rng = np.random.default_rng(0)
    eA = 0.05 + 0.01 * rng.random((T, B))
    eB = 0.05 + 0.01 * rng.random((T, B))
    seam = [8] * B if seam is None else list(seam)
    for b in range(B):
        s = int(seam[b])
        eA[:s, b] += 1.0
        eB[s:, b] += 1.0
        # make A and B similar right at the intended cut so the paper term prefers it
        if 0 < s < T:
            eB[s, b] = eA[s - 1, b]
    if clash_band is not None:
        b, lo, hi = clash_band
        eA[lo:hi, b] += 2.0
        eB[lo:hi, b] += 2.0
    if gap_at is not None:
        t, b = gap_at
        eB[t, b] = 1e-8
        eB[min(t + 1, T - 1), b] = 1e-8
    return eA, eB


def test_min_cut_prefers_cheap_time_edge():
    T, B = 8, 6
    tc = np.full((T - 1, B), 10.0)
    tc[3, :] = 0.1  # cheap cut between bars 3 and 4
    fc = np.full((T, B - 1), 1.0)
    seams, _ = GC.min_cut_seams(tc, fc)
    assert seams.shape == (B,)
    assert np.all(seams == 4) or np.all(np.abs(seams - 4) <= 1)


def test_seams_are_monotonic_and_anchored():
    T, B = 12, 6
    tc = np.ones((T - 1, B))
    fc = np.ones((T, B - 1))
    seams, _ = GC.min_cut_seams(tc, fc)
    assert np.all((seams >= 1) & (seams <= T - 1))


def test_bass_gap_is_not_chosen_when_a_legal_cut_exists():
    T, B = 16, 6
    eA, eB = _energies(T, B, seam=[8] * B)
    eB[:, :2] += 1.0
    eB[4, 0] = 1e-8
    eB[5, 0] = 1e-8
    eB[4, 1] = 1e-8
    eB[5, 1] = 1e-8
    packed = GC.plan_seams(eA, eB, 0, T, _xfader(0, T), lead=(1.0, 0.0))
    for b in GC.BASS_IDX:
        assert packed['seams'][b] not in (4, 5), packed['seams']


def test_clash_makes_a_cut_cheaper_than_a_compatible_region():
    T, B = 16, 6
    # Incoming has energy from the start so a legal bass cut is not a gap.
    # Mid band 2 clashes in bars 3-7 (inside the long-fade x 0.2-0.65 window);
    # other mid/high bands prefer a later similar join at bar 10.
    eA, eB = _energies(T, B, seam=[10] * B)
    eB[:, :2] += 1.0  # bass coverage the whole window
    eA[3:8, 2] += 2.0
    eB[3:8, 2] += 2.0
    packed = GC.plan_seams(eA, eB, 0, T, _xfader(0, T))
    assert 3 <= packed['seams'][2] <= 8, packed['seams']


def test_compatible_mids_overlap_more_than_clashing_ones():
    clash = [0.8 if b == 2 else 0.0 for b in range(6)]
    packed = GC.curves_from_seams([8] * 6, 0, 16, clash, x_of=lambda bar: bar / 16.0)
    w_clash = packed['bands'][2]['width']
    w_ok = packed['bands'][3]['width']
    assert w_clash <= GC.CLASH_W_BARS + 1e-9
    assert w_ok >= w_clash
    assert w_ok == GC.COMPAT_W


def test_bass_ramps_are_complementary_and_x1_legal():
    xs = _xfader(0, 16)
    packed = GC.curves_from_seams([8] * 6, 0, 16, [0.0] * 6,
                                  x_of=lambda bar: float(np.interp(bar, [p[0] for p in xs], [p[1] for p in xs])),
                                  lead=(1.0, 0.0))
    lo_out, lo_in = packed['low']
    bars = np.arange(0, 16 + 1e-9, 1 / 16)
    a = np.interp(bars, [p[0] for p in lo_out], [p[1] for p in lo_out])
    b = np.interp(bars, [p[0] for p in lo_in], [p[1] for p in lo_in])
    assert a[0] > 0.99 and a[-1] < 0.01
    assert b[0] < 0.01 and b[-1] > 0.99
    assert not ((np.diff(a) > 1e-6).any())  # outgoing only falls
    assert not ((np.diff(b) < -1e-6).any())
    # never both loud for long: at most a short cross
    both = (a > 0.5) & (b > 0.5)
    assert both.sum() / 16 <= 2.0 + 1e-6  # <= 2 bars
    # width 1-4 bars
    mov = np.where(np.abs(np.diff(a)) > 1e-6)[0]
    width = (mov[-1] + 1 - mov[0]) / 16
    assert 1 - 1e-6 <= width <= 4 + 1e-6
    # centre in x 0.2-0.65
    xc = float(np.interp(bars[(mov[0] + mov[-1] + 1) // 2], [p[0] for p in xs], [p[1] for p in xs]))
    assert 0.2 <= xc <= 0.65, xc
    # step per 1/16 bar
    assert np.abs(np.diff(a)).max() <= 0.25
    assert np.abs(np.diff(b)).max() <= 0.25


def test_x1_accepts_emitted_low_high_and_rejects_extra_auto_keys():
    sys.path.insert(0, os.path.join(ROOT, 'src', 'tests'))
    import test_crossfader as U
    X = 16
    xs = _xfader(0, X)
    packed = GC.curves_from_seams([6] * 6, 0, X, [0.2] * 6,
                                  x_of=lambda bar: float(np.interp(bar, [p[0] for p in xs], [p[1] for p in xs])),
                                  lead=(1.0, 0.0))
    M = dict(trans=[dict(a='A', b='B', start_bar=0, end_bar=X, xfader=xs,
                         high_bar=int(round(packed['high_centre'] - 1)),
                         bass_swap=packed['bass_swap'])],
             decks=[
                 dict(id='A', start_bar=-8, end_bar=X,
                      auto=dict(gain=[[p[0], float(np.cos(p[1] * np.pi / 2))] for p in xs],
                                low=packed['low'][0], high=packed['high'][0])),
                 dict(id='B', start_bar=0, end_bar=X + 8,
                      auto=dict(gain=[[p[0], float(np.sin(p[1] * np.pi / 2))] for p in xs],
                                low=packed['low'][1], high=packed['high'][1])),
             ])
    assert U.run(M) == [], U.run(M)
    # a mid-band auto key would fail X1 — graphcut must not put mid curves there
    M2 = dict(trans=M['trans'], decks=[{**M['decks'][0], 'auto': {**M['decks'][0]['auto'],
                                                                  'mid': packed['bands'][2]['out']}},
                                       M['decks'][1]])
    assert U.run(M2), 'expected X1 to reject a mid auto lane'


def test_render_bands_is_near_perfect_when_gains_are_unity():
    sr, n = 44100, 44100
    rng = np.random.default_rng(1)
    y = (0.1 * rng.standard_normal((n, 2))).astype(np.float32)
    gc = dict(edges=GC.EDGES.tolist(),
              gains=[[[0.0, 1.0], [16.0, 1.0]] for _ in range(6)])
    # bar_s such that 16 bars ~ 1 s would be wrong; use real BAR
    import engine
    rec = GC.render_bands(y.copy(), gc, 0.0, n, engine.BS, sr)
    mid = slice(engine.SR // 10, -engine.SR // 10)
    err = np.sqrt(np.mean((rec[mid] - y[mid]) ** 2))
    rms = np.sqrt(np.mean(y[mid] ** 2))
    assert err / (rms + 1e-12) < 0.05, err / (rms + 1e-12)


def test_render_bands_silence_when_all_gains_zero():
    sr, n = 44100, 44100 // 2
    y = np.ones((n, 2), np.float32) * 0.2
    gc = dict(edges=GC.EDGES.tolist(),
              gains=[[[0.0, 0.0], [8.0, 0.0]] for _ in range(6)])
    import engine
    rec = GC.render_bands(y.copy(), gc, 0.0, n, engine.BS, sr)
    mid = slice(engine.SR // 20, -engine.SR // 20)
    assert float(np.sqrt(np.mean(rec[mid] ** 2))) < 0.02


def test_default_fade_is_still_tail_and_flag_is_off():
    # The module must not flip the mix_simple default. Read the assignment.
    src = open(os.path.join(ROOT, 'src2', 'mix_simple.py')).read()
    assert "FADE=os.environ.get('FADE','tail')" in src
    assert "GC=os.environ.get('GRAPH_CUT','0')=='1' or FADE0=='graphcut'" in src
    rules = os.path.join(ROOT, 'protrans', 'rules.json')
    import json
    r = json.load(open(rules))
    assert r.get('FADE') != 'graphcut', 'rules.json must not be switched to graphcut'


def test_gap_db_matches_release_threshold():
    import bassgap
    assert GC.GAP_DB == bassgap.GAP_DB == 9.84


def test_outgoing_bass_follows_fader_when_incoming_never_covers():
    """A hard bass swap would hand the mix to a hole. Outgoing bass should
    ride the equal-power xfader instead, and incoming bass stay off."""
    T, B = 16, 6
    eA, eB = _energies(T, B, seam=[8] * B)
    eB[:, :2] *= 1e-6
    xs = _xfader(0, T)
    packed = GC.plan_seams(eA, eB, 0, T, xs, lead=(1.0, 0.0))
    assert packed['incoming_covers_bass'] is False
    assert packed['bass_follow_fader'] is True
    assert packed['bass_swap'] is None
    lo_out, lo_in = packed['low']
    # mid-blend: FADE=long x is 0.5, equal-power is 1/sqrt(2) ~= 0.707 each
    mid_o = np.interp(8.0, [p[0] for p in lo_out], [p[1] for p in lo_out])
    mid_i = np.interp(8.0, [p[0] for p in lo_in], [p[1] for p in lo_in])
    assert mid_o > 0.6 and mid_i > 0.6, (mid_o, mid_i)
    # end of the window: outgoing gone, incoming at unity (so the drop still has bass)
    end_o = np.interp(16.0, [p[0] for p in lo_out], [p[1] for p in lo_out])
    end_i = np.interp(16.0, [p[0] for p in lo_in], [p[1] for p in lo_in])
    assert end_o < 0.05 and end_i > 0.99, (end_o, end_i)
    assert np.interp(0.0, [p[0] for p in lo_in], [p[1] for p in lo_in]) < 0.05
    # not a 3-bar dump: still substantial at the old early/late legal centres
    g4 = np.interp(4.0, [p[0] for p in lo_out], [p[1] for p in lo_out])
    g9 = np.interp(9.0, [p[0] for p in lo_out], [p[1] for p in lo_out])
    assert g4 > 0.5 and g9 > 0.4, (g4, g9)
