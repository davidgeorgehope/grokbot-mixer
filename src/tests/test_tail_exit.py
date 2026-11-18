"""TAIL_EXIT (src2/tail_exit.py, 2026-11-15 research, off by default): shorter outgoing tail tied to the bass swap,
still one monotonic equal-power crossfader, never steeper than 3 dB/bar above -24 dB, ride rule and X1 intact."""
import os, sys, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'src2'))
sys.path.insert(0, HERE)
import tail_exit as TE
import fade_long as FL
import test_crossfader as U

RIDE_FRAC = 0.15


def _tail_x(u, FDB=22):
    if u >= 1: return 1.0
    w = u ** 1.4
    return float((1 - w) * u + w * 2 / np.pi * np.arccos(10 ** (-FDB * u ** 1.7 / 20)))


def _trans(X, xfun, swap, high=None, s=0):
    xs = [[s + k / 4, round(xfun(k / (4 * X)) if k < 4 * X else 1.0, 5)] for k in range(4 * X + 1)]
    return dict(a='A', b='B', start_bar=s, end_bar=s + X, xfader=xs, bass_swap=list(swap), swap_w=swap[1] - swap[0] - 1,  # lanes below: SW wide plus a 1-bar outgoing lead
                high_bar=high)


def _meta(t, sw=None):
    X = t['end_bar'] - t['start_bar']
    M = dict(trans=[t], decks=[dict(id='A', start_bar=-10, end_bar=t['end_bar'], auto={}),
                              dict(id='B', start_bar=0, end_bar=t['end_bar'] + 40, auto={})])
    return M


def _gain_lanes(M):
    t = M['trans'][0]
    M['decks'][0]['auto']['gain'] = [[p[0], float(np.cos(p[1] * np.pi / 2))] for p in t['xfader']]
    M['decks'][1]['auto']['gain'] = [[p[0], float(np.sin(p[1] * np.pi / 2))] for p in t['xfader']]
    c0, c1 = t['bass_swap']
    def r(up, a, b):
        return [[a + (b - a) * j / 16, float((1 - np.cos(np.pi * j / 16)) / 2 if up else (1 + np.cos(np.pi * j / 16)) / 2)] for j in range(17)]
    M['decks'][0]['auto']['low'] = r(False, c0, c1 - 1)  # outgoing leads by 1 bar (FADE=long shape)
    M['decks'][1]['auto']['low'] = r(True, c0 + 1, c1)
    return M


def _tail_checks(t):
    s, e = t['start_bar'], t['end_bar']; X = e - s
    xs = np.array(t['xfader']); bars = np.arange(s, e + 1e-9, 1.0)
    g = 20 * np.log10(np.cos(np.interp(bars, xs[:, 0], xs[:, 1]) * np.pi / 2) + 1e-9)
    steep = [float(x) for x, v in zip(np.diff(g), g[1:]) if v > -24 and x < -3]
    ride = float(np.sum(g[bars >= t['bass_swap'][1]] > -20))
    return steep, ride, RIDE_FRAC * X - 1


def _cases():
    out = []
    for X in (16, 32):
        c = 5 if X == 16 else 10  # tail planner keeps the swap centre at x 0.2-0.65 (x(c)~0.35 here)
        out.append(('tail', X, lambda u, X=X: _tail_x(u), (c - 2, c + 2)))
        sp = FL.swap_pos(X, solo=16 if X == 32 else 0) * X
        out.append(('long', X, lambda u, X=X: FL.xlong(u, X, solo=16 if X == 32 else 0), (sp - 3, sp + 1)))
    return out


def test_exit_is_earlier_or_equal_and_monotonic():
    for name, X, f, sw in _cases():
        for N in (2, 4, 6):
            t = _trans(X, f, sw); old = [list(p) for p in t['xfader']]
            info = TE.apply_one(t, N)
            xv = [p[1] for p in t['xfader']]
            assert all(b >= a - 1e-9 for a, b in zip(xv, xv[1:])), (name, X, N)
            assert xv[0] == 0 and xv[-1] == 1
            assert all(n[1] >= o[1] - 1e-9 for n, o in zip(t['xfader'], old)), 'only ever earlier/lower outgoing'
            assert info['exit_bar'] <= info['old_exit_bar'] + 1e-9


def test_tail_still_gradual_and_rides():
    for name, X, f, sw in _cases():
        for N in (1, 2, 3, 4, 6):
            t = _trans(X, f, sw); TE.apply_one(t, N)
            steep, ride, need = _tail_checks(t)
            assert not steep, (name, X, N, steep)
            assert ride >= need, (name, X, N, ride, need)


def test_x1_still_passes():
    for name, X, f, sw in _cases():
        for N in (2, 4):
            assert U.run(_gain_lanes(_meta(_trans(X, f, sw)))) == [], 'baseline must pass first'
            t = _trans(X, f, sw); TE.apply_one(t, N)
            M = _gain_lanes(_meta(t))
            assert U.run(M) == [], (name, X, N, U.run(M))


def test_short_tail_on_long_32():
    """32-bar FADE=long: N=4 gets the outgoing under -24 dB clearly earlier than the default exit."""
    X = 32; sp = FL.swap_pos(X, solo=16) * X
    t = _trans(X, lambda u: FL.xlong(u, X, solo=16), (sp - 3, sp + 1)); TE.apply_one(t, 4)
    assert t['tail_exit']['exit_bar'] < t['tail_exit']['old_exit_bar'] or t['tail_exit']['clamped_by']


def test_tail_fade_32_gets_shorter():
    X = 32; t = _trans(X, _tail_x, (5, 9)); info = TE.apply_one(t, 4)
    assert info['exit_bar'] < info['old_exit_bar'] - 4, info


def test_high_swap_x_guard():
    X = 32; t = _trans(X, _tail_x, (5, 9), high=20); TE.apply_one(t, 2)
    xs = np.array(t['xfader'])
    assert np.interp(22, xs[:, 0], xs[:, 1]) <= 0.9 + 1e-9


def test_off_by_default():
    src = open(os.path.join(HERE, '..', '..', 'src2', 'mix_simple.py')).read()
    assert "TE=float(os.environ.get('TAIL_EXIT',0) or 0)" in src and 'if TE>0 and not GC:' in src
    import json
    rules = json.load(open(os.path.join(HERE, '..', '..', 'protrans', 'rules.json')))
    # Code still defaults to 0 when the env is unset. rules.json sets TAIL_EXIT 6
    # (kept 2026-11-17 daily) so official recreates enable it via apply_rules.
    assert int(rules.get('TAIL_EXIT') or 0) == 6
