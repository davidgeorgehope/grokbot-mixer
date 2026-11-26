import os, sys, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, '/workspace/mixes/src2')
import pro_fade as PF


def test_flag_off_by_default():
    assert PF.flag_on({}) is False
    assert PF.flag_on({'PRO_FADE': '0'}) is False
    assert PF.flag_on({'PRO_FADE': '1'}) is True


def test_build_xfader_monotonic_and_rate_capped():
    for X in (16, 24, 32, 40):
        xs, info = PF.build_xfader(100, 100 + X, 100 + 3, 100 + 4, entry_db=-10.0, shelf_db=-11.0, exit_slope=2.0)
        assert xs[0] == [100.0, 0.0]
        assert xs[-1] == [float(100 + X), 1.0]
        vals = [p[1] for p in xs]
        assert all(b >= a - 1e-9 for a, b in zip(vals, vals[1:]))
        # Verify <= 3.0 dB / beat on incoming & outgoing above -24 dB floor
        bars = np.arange(100.0, 100.0 + X + 1e-9, 1.0 / 16.0)
        xv = np.interp(bars, [p[0] for p in xs], [p[1] for p in xs])
        ga_db = np.maximum(20.0 * np.log10(np.maximum(np.cos(xv * np.pi / 2.0), 1e-6)), -24.0)
        gb_db = np.maximum(20.0 * np.log10(np.maximum(np.sin(xv * np.pi / 2.0), 1e-6)), -24.0)
        assert np.max(np.abs(ga_db[4:] - ga_db[:-4])) <= 3.05
        assert np.max(np.abs(gb_db[4:] - gb_db[:-4])) <= 3.05


def test_high_lane_keeps_unity_at_endpoints_and_boosts_shelf():
    xs, _ = PF.build_xfader(100, 132, 107, 109, entry_db=-10.0, shelf_db=-11.0, exit_slope=2.0, anchor_early=True)
    hi_out = PF._high_lane_out(xs, 6.5)
    hi_in = PF._high_lane_in(xs, 107, 6.5)
    assert hi_out[0][1] == 1.0 and hi_out[-1][1] == 1.0
    assert hi_in[0][1] == 1.0 and hi_in[-1][1] == 1.0
    # Effective high gain <= 1.0 (0 dB) everywhere
    for (b, x), (_, gho), (_, ghi) in zip(xs, hi_out, hi_in):
        assert np.cos(x * np.pi / 2.0) * gho <= 1.001
        assert np.sin(x * np.pi / 2.0) * ghi <= 1.001


def test_apply_shapes_gain_low_high_when_flagged():
    decks = [
        dict(id='A', start_bar=0, end_bar=132, full_map=[(k, 'mix') for k in range(132)], auto={'gain': [], 'low': []}),
        dict(id='B', start_bar=100, end_bar=200, full_map=[(k, 'mix') for k in range(100)], auto={'gain': [], 'low': []}),
    ]
    trans = [dict(a='A', b='B', start_bar=100, end_bar=132, swap_bar=108, swap_w=3.0, bass_swap=[106.5, 109.5], tech='base')]
    res = PF.apply(decks, trans, params=dict(entry_db=-10.0, shelf_db=-11.0, exit_slope=2.0, high_offset_db=6.5, bass_cut_db=-24.0))
    assert len(res) == 1
    assert 'high' in decks[0]['auto'] and 'high' in decks[1]['auto']
    lo_a = [pt[1] for pt in decks[0]['auto']['low']]
    assert lo_a[0] == 1.0 and lo_a[-1] == 0.0
    assert all(b <= a + 1e-6 for a, b in zip(lo_a, lo_a[1:]))
    assert decks[1]['auto']['low'][-1][1] == 1.0


def _two_decks(b_lows_db, a_lows_db=-18.0, nB=100):
    decks = [
        dict(id='A', start_bar=0, end_bar=132, full_map=[(k, 'mix') for k in range(132)], auto={'gain': [], 'low': []}),
        dict(id='B', start_bar=100, end_bar=200, full_map=[(k, 'mix') for k in range(nB)], auto={'gain': [], 'low': []}),
    ]
    trans = [dict(a='A', b='B', start_bar=100, end_bar=132, swap_bar=108, swap_w=4.0, bass_swap=[106.0, 110.0], tech='base')]
    lows = {'A': [a_lows_db] * 132, 'B': list(b_lows_db) + [-18.0] * (nB - len(b_lows_db))}
    return decks, trans, lows


P0 = dict(entry_db=-8.5, shelf_db=-10.0, exit_slope=2.5, high_offset_db=7.0, bass_cut_db=-24.0)


def test_new_bass_params_default_off_and_read_from_env():
    p = PF.params_from_env({})
    assert p['bass_rel_db'] == 0.0 and p['bass_sw'] == 0.0
    p = PF.params_from_env({'PRO_FADE_BASS_REL': '8', 'PRO_FADE_BASS_SW': '1'})
    assert p['bass_rel_db'] == 8.0 and p['bass_sw'] == 1.0


def test_bass_rel_off_is_identical_to_fit2_lanes():
    d1, t1, lows = _two_decks([-40.0] * 100)
    d2, t2, _ = _two_decks([-40.0] * 100)
    PF.apply(d1, t1, params=dict(P0))
    PF.apply(d2, t2, params=dict(P0, bass_rel_db=0.0, bass_sw=0.0), lows_of=lows.get)
    assert d1 == d2


def _lane(pts, b):
    return float(np.interp(b, [p[0] for p in pts], [p[1] for p in pts]))


def test_bass_rel_holds_outgoing_under_bass_light_incoming():
    # incoming intro lows 20 dB under the outgoing body: a fixed -24 dB cut would meet it at equal level
    rel = 8.0
    decks, trans, lows = _two_decks([-38.0] * 100)
    ref, tref, _ = _two_decks([-38.0] * 100)
    PF.apply(ref, tref, params=dict(P0))
    PF.apply(decks, trans, params=dict(P0, bass_rel_db=rel), lows_of=lows.get)
    lo_a, lo_a_ref, lo_b = decks[0]['auto']['low'], ref[0]['auto']['low'], decks[1]['auto']['low']
    xs = trans[0]['xfader']
    for b in np.arange(112.0, 131.0, 0.25):
        assert _lane(lo_a, b) <= _lane(lo_a_ref, b) + 1e-4          # never raises the lane (5-dp rounding)
        x = _lane(xs, b)
        a_net = -18.0 + 20 * np.log10(max(np.cos(x * np.pi / 2) * _lane(lo_a, b), 1e-9))
        b_net = -38.0 + 20 * np.log10(max(np.sin(x * np.pi / 2) * _lane(lo_b, b), 1e-9))
        assert a_net <= b_net - rel + 0.5
    vals = [p[1] for p in lo_a]
    assert all(b2 <= a2 + 1e-6 for a2, b2 in zip(vals, vals[1:]))  # still monotone down
    assert vals[0] == 1.0 and vals[-1] == 0.0


def test_bass_rel_leaves_lane_alone_when_incoming_bass_is_strong():
    decks, trans, lows = _two_decks([-16.0] * 100)
    ref, tref, _ = _two_decks([-16.0] * 100)
    PF.apply(ref, tref, params=dict(P0))
    PF.apply(decks, trans, params=dict(P0, bass_rel_db=8.0), lows_of=lows.get)
    for b in np.arange(100.0, 132.0, 0.25):
        assert abs(_lane(decks[0]['auto']['low'], b) - _lane(ref[0]['auto']['low'], b)) < 0.02


def test_bass_sw_shortens_both_low_ramps():
    decks, trans, lows = _two_decks([-16.0] * 100)
    PF.apply(decks, trans, params=dict(P0, bass_sw=1.0), lows_of=lows.get)
    lo_b = decks[1]['auto']['low']
    rise = [p[0] for p in lo_b if 0.0 < p[1] < 1.0]
    assert max(rise) - min(rise) <= 1.0 + 1e-6
    lo_a = decks[0]['auto']['low']
    first_drop = [p[0] for p in lo_a if p[1] < 1.0][0]
    first_shelf = [p[0] for p in lo_a if abs(p[1] - lo_a[16][1]) < 1e-9][0]
    assert first_shelf - first_drop <= 1.0 + 1e-6


def test_bass_rel_mid_off_by_default_and_caps_earlier_inside_the_handoff():
    assert PF.params_from_env({})['bass_rel_mid'] == 0.0
    assert PF.params_from_env({'PRO_FADE_BASS_REL_MID': '1'})['bass_rel_mid'] == 1.0
    end, tend, lows = _two_decks([-38.0] * 100)
    mid, tmid, _ = _two_decks([-38.0] * 100)
    PF.apply(end, tend, params=dict(P0, bass_rel_db=8.0), lows_of=lows.get)
    PF.apply(mid, tmid, params=dict(P0, bass_rel_db=8.0, bass_rel_mid=1.0), lows_of=lows.get)
    la_end, la_mid = end[0]['auto']['low'], mid[0]['auto']['low']
    diffs = [_lane(la_end, b) - _lane(la_mid, b) for b in np.arange(100.0, 132.0, 0.25)]
    assert min(diffs) >= -1e-4          # never raises the lane vs the end-of-ramp cap
    assert max(diffs) > 1e-3            # and actually cuts earlier, inside the ramp tail
    vals = [p[1] for p in la_mid]
    assert all(b2 <= a2 + 1e-6 for a2, b2 in zip(vals, vals[1:]))
