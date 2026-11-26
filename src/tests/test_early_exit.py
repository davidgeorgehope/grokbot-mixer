"""Tests for EARLY_EXIT=1 (src2/early_exit.py), compat both-floor fix, and picker_1125_early_exit."""
import json
import os
import sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
SRC2 = os.path.join(ROOT, 'src2')
PT = os.path.join(ROOT, 'protrans')
REP = os.path.join(PT, 'replica')
for p in (HERE, SRC2, PT, REP):
    if p not in sys.path:
        sys.path.insert(0, p)

import early_exit as EE
import test_crossfader as U


def _make_decks_and_trans(s=120, e=160, na=210, ib=16, d1_b=32, high_bar=None, fade='tail'):
    X = e - s
    xs = [[s + k / 4.0, round(k / (4.0 * X), 5)] for k in range(4 * X + 1)]
    t = dict(
        a='A', b='B', start_bar=float(s), end_bar=float(e),
        xfader=xs, swap_w=3.0, swap_bar=s + 16, swap_ofs=0.0, swap_phrase=False,
        bass_swap=[s + 14.0, s + 17.0], high_bar=high_bar, fade=fade, notes=[],
    )
    d0 = dict(
        id='A', start_bar=0.0, end_bar=float(e),
        full_map=[[k, 0] for k in range(e)],
        auto=dict(
            gain=[[p[0], float(np.cos(p[1] * np.pi / 2))] for p in xs],
            low=EE._ramp(s + 15.0, False, 3.0),
        ),
    )
    d1 = dict(
        id='B', start_bar=float(s), end_bar=float(s + 100),
        full_map=[[ib + k, 0] for k in range(100)],
        auto=dict(
            gain=[[p[0], float(np.sin(p[1] * np.pi / 2))] for p in xs],
            low=EE._ramp(s + 16.0, True, 3.0),
        ),
    )
    secs = {
        'A': dict(music_end=na, n_bars=na, drops=[[48, 112], [144, 200]]),
        'B': dict(music_end=180, n_bars=180, drop1=d1_b, drops=[[d1_b, 96]]),
    }
    return [d0, d1], [t], secs


def test_flag_off_by_default_and_noop():
    old = os.environ.pop('EARLY_EXIT', None)
    try:
        assert not EE.flag_on()
        decks, trans, secs = _make_decks_and_trans()
        before = json.loads(json.dumps(trans))
        assert EE.apply(decks, trans, secs_of=secs.get) == []
        assert trans == before
    finally:
        if old is not None:
            os.environ['EARLY_EXIT'] = old


def test_build_xfader_x1_and_gradual_tail_and_drop_hold():
    for X in (36, 40, 44):
        for k_drop in (10, 16, 20):
            s, e = 120.0, 120.0 + X
            decks, trans, secs = _make_decks_and_trans(s=int(s), e=int(e), d1_b=16 + int(k_drop), high_bar=140.0)
            old = os.environ.get('EARLY_EXIT')
            os.environ['EARLY_EXIT'] = '1'
            try:
                res = EE.apply(decks, trans, secs_of=secs.get)
            finally:
                if old is None:
                    os.environ.pop('EARLY_EXIT', None)
                else:
                    os.environ['EARLY_EXIT'] = old
            assert len(res) == 1
            M = dict(decks=decks, trans=trans)
            errs = U.run(M)
            assert errs == [], f"X={X} k_drop={k_drop} X1 errors: {errs}"

            # Verify gradual outgoing tail <= 3.0 dB/bar above -24 dB
            xs = np.array(trans[0]['xfader'])
            bars = np.arange(s, e + 1e-9, 1.0)
            g_out = 20.0 * np.log10(np.cos(np.interp(bars, xs[:, 0], xs[:, 1]) * np.pi / 2) + 1e-9)
            steep = [float(dx) for dx, v in zip(np.diff(g_out), g_out[1:]) if v > -24.0 and dx < -3.0]
            assert steep == [], f"X={X} k_drop={k_drop} steep outgoing steps: {steep}"

            # Verify outgoing holds near -15 dB under incoming drop (when X >= 36)
            if X >= 36:
                t_hold = res[0]['t_hold']
                t_exit0 = res[0]['t_exit0']
                if t_exit0 - t_hold >= 2.0:
                    mid_h = 0.5 * (t_hold + t_exit0)
                    g_mid = float(20.0 * np.log10(np.cos(np.interp(mid_h, xs[:, 0], xs[:, 1]) * np.pi / 2) + 1e-9))
                    assert -16.5 <= g_mid <= -14.0, f"expected ~-15 dB hold, got {g_mid}"


def test_apply_skips_outro_and_graphcut():
    old = os.environ.get('EARLY_EXIT')
    os.environ['EARLY_EXIT'] = '1'
    try:
        # Outro blend (na - out_end = 10 < 24): untouched
        decks, trans, secs = _make_decks_and_trans(s=168, e=200, na=210)
        assert EE.apply(decks, trans, secs_of=secs.get) == []
        assert trans[0]['fade'] == 'tail'

        # Standard X=32 blend: untouched (base X<=32 never drifts)
        decks32, trans32, secs32 = _make_decks_and_trans(s=120, e=152, na=210)
        assert EE.apply(decks32, trans32, secs_of=secs32.get) == []
        assert trans32[0]['fade'] == 'tail'

        # Graphcut blend: untouched
        decks2, trans2, secs2 = _make_decks_and_trans(s=120, e=160, na=210, fade='graphcut')
        assert EE.apply(decks2, trans2, secs_of=secs2.get) == []
    finally:
        if old is None:
            os.environ.pop('EARLY_EXIT', None)
        else:
            os.environ['EARLY_EXIT'] = old


def test_select_compatible_picker_window_both_fix():
    import recreate
    default_win = ['n', 224, None, 16, 16]
    w_cand = ['n', 168, None, 16, 40]
    w_bad_o1 = ['n', 160, None, 16, 40]
    w_bad_seam = ['n', 164, None, 16, 40]
    w_bad_pump = ['n', 172, None, 16, 40]
    w_bad_r = ['n', 176, None, 16, 40]
    cs = [
        dict(win=default_win, pen=78.0, V=0, R=0.18, HB=False, both=8, seam_fail=0, early_exit=0),
        dict(win=w_bad_o1, pen=75.0, V=0, R=0.45, HB=False, both=7, seam_fail=0, early_exit=1, pred_vdip=2.0),
        dict(win=w_bad_seam, pen=95.0, V=0, R=0.45, HB=False, both=9, seam_fail=1, early_exit=1, pred_vdip=2.0),
        dict(win=w_bad_pump, pen=20.0, V=0, R=0.45, HB=False, both=12, seam_fail=0, early_exit=1, pred_vdip=4.8),
        dict(win=w_bad_r, pen=20.0, V=0, R=0.19, HB=False, both=12, seam_fail=0, early_exit=1, pred_vdip=2.0),
        dict(win=w_cand, pen=82.0, V=0, R=0.50, HB=False, both=9, seam_fail=0, early_exit=1, pred_vdip=2.1),
    ]
    hit, idx, tried = recreate.select_compatible_picker_window(
        'a', 'b', [w_bad_o1, w_bad_seam, w_bad_pump, w_bad_r, w_cand], cs, default_win,
        dc_eval=lambda *a: {'level': 'clean'},
    )
    assert hit is not None and hit['win'] == w_cand and idx == 4
    assert 'both=7<8' in tried[0]['reasons']
    assert any('pen=' in r for r in tried[1]['reasons'])
    assert any('pred_vdip=' in r for r in tried[2]['reasons'])
    assert any('R=0.19<0.25' in r for r in tried[3]['reasons'])

    # Standard X=16 non-early-exit window keeps strict both>=11 and raw pen cap
    w_std16 = ['n', 208, None, 16, 16]
    cs2 = [
        dict(win=default_win, pen=20.0, V=0, R=0.45, HB=False, both=16, seam_fail=0, early_exit=0),
        dict(win=w_std16, pen=85.0, V=0, R=0.50, HB=False, both=9, seam_fail=0, early_exit=0),
        dict(win=w_cand, pen=85.0, V=0, R=0.50, HB=False, both=9, seam_fail=0, early_exit=1, pred_vdip=1.8),
    ]
    hit2, idx2, tried2 = recreate.select_compatible_picker_window(
        'a', 'b', [w_std16, w_cand], cs2, default_win, dc_eval=lambda *a: {'level': 'clean'},
    )
    assert hit2 is not None and hit2['win'] == w_cand and idx2 == 1
    assert 'both=9<11' in tried2[0]['reasons']


def test_apply_rules_forwards_early_exit_without_touching_rules():
    import recreate
    rules_before = open('/workspace/mixes/protrans/rules.json').read()
    env = recreate.apply_rules({'EARLY_EXIT': 1, 'EARLY_EXIT_HOLD_DB': -15.0})
    assert env['EARLY_EXIT'] == '1'
    assert env['EARLY_EXIT_HOLD_DB'] == '-15.0'
    assert open('/workspace/mixes/protrans/rules.json').read() == rules_before


def test_early_exit_shortlist_respects_safe_vs_early():
    import picker_1125_early_exit as PEE
    from test_picker_1125_followup import _sample_row
    r = _sample_row()
    # _sample_row has d1_b=32, na=220, dex=205, dX=16
    class _DummyReg:
        def predict(self, X):
            return np.zeros(len(X))
    risks = [100.0] * len(r['E'])
    # Safe outro choice (je == Edix) -> keeps 16-bar default shortlist
    rk_safe = PEE._early_exit_cands_for_row(r, r['Edix'], r['Cdix'], _DummyReg(), 0.2, 100.0, 205.0, risks, k_max=6)
    assert all(w[4] == 16 for w in rk_safe)

    # Early-exit breakdown choice -> generates 32..44 bar drop1-aligned windows
    je = next(i for i, c in enumerate(r['E']) if abs(c['v'] - 125.0) <= 8)
    rk_ee = PEE._early_exit_cands_for_row(r, je, r['Cdix'], _DummyReg(), 0.85, 125.0, 205.0, risks, k_max=6)
    assert rk_ee and all(36 <= w[4] <= 44 for w in rk_ee)


def test_predict_dips_no_double_bass_subtraction():
    """mix_simple.F()[0] is already >150 Hz high-band, not full-band all.
    Double-subtracting loA/loB caused false V-dips whenever lo > hi."""
    X = 40
    xs_ee, info = EE.build_xfader(0.0, float(X), 16.0)
    pts = ([p[0] for p in xs_ee], [p[1] for p in xs_ee])
    # Flat total energy (-18 dB) where bar 10 has heavy sub (lo=-19, hi=-25 -> lo > hi)
    allA = np.full(80, -18.0)
    loA = np.full(80, -24.0)
    loA[10] = -19.0
    hiA = 10.0 * np.log10(np.maximum(10.0 ** (allA / 10.0) - 10.0 ** (loA / 10.0), 1e-10))
    allB = np.full(80, -18.0)
    loB = np.full(80, -24.0)
    hiB = 10.0 * np.log10(np.maximum(10.0 ** (allB / 10.0) - 10.0 ** (loB / 10.0), 1e-10))
    wa = list(range(0, X))
    wb = list(range(0, X))
    pvd, _ = EE.predict_dips(hiA, loA, hiB, loB, wa, wb, pts, info)
    assert pvd < 1.0, f"expected flat full-band level (pvd<1.0), got {pvd}"


def test_predict_dips_ignores_natural_breakdown_but_catches_engine_hole():
    """pred_ldip must not blame early_exit for Track A's own post-drop-1 breakdown
    before c_in, while still catching a real bass hole when swapping onto silent B."""
    X = 40
    xs_ee, info = EE.build_xfader(0.0, float(X), 16.0)
    pts = ([p[0] for p in xs_ee], [p[1] for p in xs_ee])
    wa = list(range(40, 40 + X))
    wb = list(range(0, X))

    # Case A: Drop 1 before wa[0] (-15 dB), Track A natural breakdown wa[0..15] (-58 dB),
    # Track B drops into bass at k=16 (-15 dB). Engine causes no bass hole.
    loA = np.full(100, -15.0)
    loA[40:58] = -58.0
    hiA = np.full(100, -20.0)
    loB = np.full(100, -55.0)
    loB[16:] = -15.0
    hiB = np.full(100, -20.0)
    _, pld_ok = EE.predict_dips(hiA, loA, hiB, loB, wa, wb, pts, info)
    assert pld_ok < 8.0, f"natural Track A breakdown falsely flagged as bass hole: {pld_ok}"

    # Case B: Track A stays loud (-15 dB), engine swaps at c_in onto silent Track B (-55 dB).
    loA_loud = np.full(100, -15.0)
    loB_dead = np.full(100, -55.0)
    _, pld_hole = EE.predict_dips(hiA, loA_loud, hiB, loB_dead, wa, wb, pts, info)
    assert pld_hole > 32.0, f"real engine bass hole missed: {pld_hole}"


def test_build_xfader_avoids_early_pre_drop_vanish_on_intro_dip():
    """Regression for pola02_blocked_ee: an incoming intro hook followed by a quiet
    pre-drop build dip must not jump to -8 dB at bar 4 and vanish before Drop 1."""
    import hardcheck as HC
    X = 40
    xs_ee, info = EE.build_xfader(0.0, float(X), 16.0)
    pts_x = [p[0] for p in xs_ee]
    pts_y = [p[1] for p in xs_ee]
    # Simulate pola02-like incoming track: intro hook bars 0..3 (-25.6 dB), pre-drop dip
    # bars 4..14 (-29..-36.6 dB), Drop 1 from bar 16 (-16 dB) while Deck A sits at ~-23 dB.
    srcB = np.full(X, -16.0)
    srcB[:4] = [-28.0, -27.4, -27.5, -25.6]
    srcB[4:16] = [-29.9, -29.1, -29.1, -29.8, -30.2, -29.4, -29.2, -32.1, -31.9, -35.6, -36.6, -34.7]
    alA = np.full(X, -23.5)
    alB = np.array([
        float(srcB[k]) + 20.0 * np.log10(float(np.sin(np.interp(k + 0.5, pts_x, pts_y) * np.pi / 2.0)) + 1e-9)
        for k in range(X)
    ])
    # Early bar 3 must stay tucked below audibility (-15 dB under Deck A), not teased then vanished
    assert alB[3] < alA[3] - 18.0, f"bar 3 exposed too loud before pre-drop dip: alB={alB[3]:.1f} vs alA={alA[3]:.1f}"
    assert HC.incoming_vanish(alB, alA, 0, X) == 0.0
