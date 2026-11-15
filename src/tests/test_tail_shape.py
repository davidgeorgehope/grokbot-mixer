"""TAIL_SHALLOW (src2/tail_shape.py, 2026-11-15 research, off by default): shallower outgoing
fade after the exit starts, residual may extend past the window, guards intact."""
import os, sys, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'src2'))
sys.path.insert(0, HERE)
import tail_shape as TS
import tail_exit as TE
import fade_long as FL
import test_crossfader as U
import test_tail_exit as E


def test_shallower_than_default_and_monotonic():
    for name, X, f, sw in E._cases():
        t = E._trans(X, f, sw); old = [list(p) for p in t['xfader']]
        info = TS.apply_one(t, 1.0)
        xv = [p[1] for p in t['xfader']]
        assert all(b >= a - 1e-9 for a, b in zip(xv, xv[1:])), (name, X)
        # inside the original window, outgoing is at or louder than the default (x at or below old)
        old_d = {round(b, 5): x for b, x in old}
        for b, x in t['xfader']:
            if b in old_d:
                assert x <= old_d[b] + 1e-6, (name, X, b, x, old_d[b])
        assert info['exit_bar'] >= info['old_exit_bar'] - 1e-9


def test_still_gradual_and_rides():
    for name, X, f, sw in E._cases():
        t = E._trans(X, f, sw); TS.apply_one(t, 1.0)
        steep, ride, need = E._tail_checks(t)
        assert not steep, (name, X, steep)
        assert ride >= need, (name, X, ride, need)


def test_x1_still_passes():
    for name, X, f, sw in E._cases():
        t = E._trans(X, f, sw); TS.apply_one(t, 1.0)
        M = E._gain_lanes(E._meta(t))
        assert U.run(M) == [], (name, X, U.run(M))


def test_long_16_leaves_residual_instead_of_silence():
    """16-bar FADE=long: R=1 keeps the outgoing clearly audible at the old window end."""
    X = 16; sp = FL.swap_pos(X, solo=0) * X
    t = E._trans(X, lambda u: FL.xlong(u, X, solo=0), (sp - 3, sp + 1))
    old_end, old_exit = t['end_bar'], TE.exit_bar(t['xfader'], -24)
    info = TS.apply_one(t, 1.0)
    xs = np.array(t['xfader'])
    g_at_old_end = float(TE._db(np.interp(old_end, xs[:, 0], xs[:, 1])))
    assert g_at_old_end > -24, (g_at_old_end, info)
    assert info['exit_bar'] > old_exit + 2, info
    assert t['end_bar'] > old_end + 2


def test_off_by_default():
    src = open(os.path.join(HERE, '..', '..', 'src2', 'mix_simple.py')).read()
    assert "TS=float(os.environ.get('TAIL_SHALLOW',0) or 0)" in src
    import json
    rules = json.load(open(os.path.join(HERE, '..', '..', 'protrans', 'rules.json')))
    assert 'TAIL_SHALLOW' not in rules and 'TAIL_EXIT' not in rules
