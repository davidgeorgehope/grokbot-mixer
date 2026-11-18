"""SNAP_IN (src2/snap_in.py, 2026-11-15 research, off by default): late legal incoming
snap + shallow outgoing hold, guards intact, X1 never loosened."""
import os, sys, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'src2'))
sys.path.insert(0, HERE)
import snap_in as SI
import tail_exit as TE
import fade_long as FL
import test_crossfader as U
import test_tail_exit as E


def test_monotonic_zero_to_one():
    for name, X, f, sw in E._cases():
        t = E._trans(X, f, sw)
        info = SI.apply_one(t, hold_db=12)
        xv = [p[1] for p in t['xfader']]
        assert all(b >= a - 1e-9 for a, b in zip(xv, xv[1:])), (name, X, xv)
        assert xv[0] <= 1e-6 and xv[-1] >= 1 - 1e-6
        assert info is not None and 'changed' in info


def test_still_gradual_and_rides():
    for name, X, f, sw in E._cases():
        t = E._trans(X, f, sw); SI.apply_one(t, hold_db=12)
        steep, ride, need = E._tail_checks(t)
        assert not steep, (name, X, steep, t.get('snap_in'))
        # ride is measured on the original window in _tail_checks
        assert ride >= need or t['snap_in'].get('clamped_by') == 'ride', (name, X, ride, need, t['snap_in'])


def test_x1_still_passes():
    for name, X, f, sw in E._cases():
        t = E._trans(X, f, sw); SI.apply_one(t, hold_db=12)
        M = E._gain_lanes(E._meta(t))
        assert U.run(M) == [], (name, X, U.run(M), t.get('snap_in'))


def test_incoming_rise_stays_under_x1():
    """Designed incoming rise never exceeds 3 dB/beat, even when the pro's 1-bar slam would."""
    for name, X, f, sw in E._cases():
        t = E._trans(X, f, sw); SI.apply_one(t, hold_db=12)
        if t['snap_in'].get('clamped_by'):
            continue
        xs = np.array(t['xfader'], float)
        fb = np.arange(t['start_bar'], t['end_bar'] + 1e-9, 1 / 16)
        gi = np.maximum(20 * np.log10(np.maximum(np.sin(np.interp(fb, xs[:, 0], xs[:, 1]) * np.pi / 2), 1e-6)), -24)
        if len(gi) > 4:
            step = float(np.abs(gi[4:] - gi[:-4]).max())
            assert step <= 3.0 + 1e-9, (name, X, step, t['snap_in'])


def test_bass_swap_centre_stays_in_x1_window():
    for name, X, f, sw in E._cases():
        t = E._trans(X, f, sw); SI.apply_one(t, hold_db=12)
        if not t.get('bass_swap'):
            continue
        xs = np.array(t['xfader'], float)
        for c in SI.swap_centres(t):
            xc = float(np.interp(c, xs[:, 0], xs[:, 1]))
            assert 0.2 - 1e-6 <= xc <= 0.65 + 1e-6, (name, X, c, xc, t['snap_in'])


def test_long_16_holds_outgoing_instead_of_dumping():
    """16-bar FADE=long: outgoing still audible at the old window end (shallow hold + residual)."""
    X = 16
    sp = FL.swap_pos(X, solo=0) * X
    t = E._trans(X, lambda u: FL.xlong(u, X, solo=0), (sp - 3, sp + 1))
    old_end = t['end_bar']
    g_old = float(TE._db(np.interp(old_end, *np.array(t['xfader']).T)))
    info = SI.apply_one(t, hold_db=12)
    xs = np.array(t['xfader'])
    g_at_old_end = float(TE._db(np.interp(old_end, xs[:, 0], xs[:, 1])))
    assert g_at_old_end > -18, (g_at_old_end, g_old, info)
    assert info['changed']
    assert t['end_bar'] >= old_end - 1e-9
    # incoming around the swap is already near the hold (much louder than a 16-bar crawl's mid-window)
    inc = float(20 * np.log10(np.sin(np.interp(t['bass_swap'][1], xs[:, 0], xs[:, 1]) * np.pi / 2) + 1e-9))
    assert inc > -8, (inc, info)


def test_does_not_loosen_x1_for_a_one_bar_slam():
    """A requested rise that would be a 1-bar slam is not rendered; X1 still passes."""
    X = 16
    sp = FL.swap_pos(X, solo=0) * X
    t = E._trans(X, lambda u: FL.xlong(u, X, solo=0), (sp - 3, sp + 1))
    # rise=12 dB/beat would be a 1-bar 24 dB slam; apply_one must cap to the legal rate
    info = SI.apply_one(t, hold_db=12, rise=12.0)
    M = E._gain_lanes(E._meta(t))
    # either clamped, or internally used the legal rise — X1 must pass either way
    assert U.run(M) == [], (U.run(M), info)
    xs = np.array(t['xfader'], float)
    fb = np.arange(t['start_bar'], t['end_bar'] + 1e-9, 1 / 16)
    gi = np.maximum(20 * np.log10(np.maximum(np.sin(np.interp(fb, xs[:, 0], xs[:, 1]) * np.pi / 2), 1e-6)), -24)
    step = float(np.abs(gi[4:] - gi[:-4]).max()) if len(gi) > 4 else 0
    assert step <= 3.0 + 1e-9, (step, info)


def test_off_by_default():
    src = open(os.path.join(HERE, '..', '..', 'src2', 'mix_simple.py')).read()
    assert "SI=float(os.environ.get('SNAP_IN',0) or 0)" in src
    assert 'if SI>0 and not GC:' in src
    import json
    rules = json.load(open(os.path.join(HERE, '..', '..', 'protrans', 'rules.json')))
    assert 'SNAP_IN' not in rules and 'SNAP_IN_DB' not in rules
    assert 'TAIL_SHALLOW' not in rules  # TAIL_EXIT 6 was kept 2026-11-17; not a SNAP_IN default


def test_hold_extra_extends_plateau_without_loosening_x1():
    """SNAP_IN_HOLD keeps the -12 dB plateau past the window, then the usual
    residual. Default (hold_extra=0) is unchanged. X1 is not loosened.
    """
    import math
    # same 16-bar FADE=long case the other tests use
    name, X, f, sw = next(c for c in E._cases() if c[0] == 'long' and c[1] == 16)
    t0 = E._trans(X, f, sw)
    info0 = SI.apply_one(t0, hold_db=12, hold_extra=0)
    t1 = E._trans(X, f, sw)
    info1 = SI.apply_one(t1, hold_db=12, hold_extra=16)
    assert info0.get('clamped_by') is None and info1.get('clamped_by') is None
    # default residual still sits near ext_cap (about 4-8 bars past e0)
    assert info0['extended_by'] <= 8.0 + 1e-6
    # 16-bar plateau plus residual is clearly longer
    assert info1['extended_by'] >= 16.0
    assert info1['extended_by'] <= 16.0 + 8.0 + 1e-6
    e0 = 16.0
    # still at hold around e0+8 (mid-plateau), gone after residual
    def out_db(xs, bar):
        import numpy as np
        xs = np.array(xs, float)
        x = float(np.interp(bar, xs[:, 0], xs[:, 1]))
        return 20 * math.log10(max(math.cos(x * math.pi / 2), 1e-9))
    assert out_db(t1['xfader'], e0 + 8) > -15.0
    assert out_db(t1['xfader'], e0 + 8) < -8.0
    # incoming rise still respects the 3.0 dB/beat cap
    assert SI.RISE <= 3.0
