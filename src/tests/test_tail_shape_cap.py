"""TAIL_SHALLOW_CAP / TAIL_SHALLOW_GATE (src2/tail_shape.py, 2026-11-16 research, off by default):
capped shallow outgoing residual, gated to blends whose exit already sits at the window end."""
import os, sys, json, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'src2'))
sys.path.insert(0, HERE)
import tail_shape as TS
import tail_exit as TE
import fade_long as FL
import test_crossfader as U
import test_tail_exit as E


def _long16():
    X = 16; sp = FL.swap_pos(X, solo=0) * X
    return E._trans(X, lambda u: FL.xlong(u, X, solo=0), (sp - 3, sp + 1))


def _long32_solo():
    X = 32; sp = FL.swap_pos(X, solo=16) * X
    return E._trans(X, lambda u: FL.xlong(u, X, solo=16), (sp - 3, sp + 1))


def _all_points_steps(t):
    xs = np.array(t['xfader']); bars = np.arange(xs[0, 0], xs[-1, 0] + 1e-9, 1.0)
    g = 20 * np.log10(np.cos(np.interp(bars, xs[:, 0], xs[:, 1]) * np.pi / 2) + 1e-9)
    return [float(d) for d, v in zip(np.diff(g), g[1:]) if v > -24 and d < -3]


def test_cap_bounds_extension():
    for cap in (4, 8):
        for name, X, f, sw in E._cases():
            t = E._trans(X, f, sw); end0 = t['end_bar']
            info = TS.apply_one(t, 1.0, cap=cap)
            assert t['end_bar'] <= end0 + cap + 1e-9, (name, X, cap, t['end_bar'])
            assert info['extended_by'] <= cap + 1e-9
            assert t['xfader'][-1][1] == 1.0


def test_cap_monotonic_lift_only_and_gradual_everywhere():
    for cap in (4, 8):
        for name, X, f, sw in E._cases():
            t = E._trans(X, f, sw); old = {round(b, 5): x for b, x in t['xfader']}
            TS.apply_one(t, 1.0, cap=cap)
            xv = [p[1] for p in t['xfader']]
            assert all(b >= a - 1e-9 for a, b in zip(xv, xv[1:])), (name, X, cap)
            for b, x in t['xfader']:
                if round(b, 5) in old:
                    assert x <= old[round(b, 5)] + 1e-6
            # gradual rule holds over the residual too, not only inside the window
            assert not _all_points_steps(t), (name, X, cap, _all_points_steps(t))
            steep, ride, need = E._tail_checks(t)
            assert not steep and ride >= need


def test_cap_x1_still_passes():
    for cap in (4, 8):
        for gate in (None, 'end'):
            for name, X, f, sw in E._cases():
                t = E._trans(X, f, sw); TS.apply_one(t, 1.0, cap=cap, gate=gate)
                M = E._gain_lanes(E._meta(t))
                assert U.run(M) == [], (name, X, cap, gate, U.run(M))


def test_cap_shorter_than_uncapped_but_still_residual():
    t1 = _long16(); i1 = TS.apply_one(t1, 1.0)
    for cap in (4, 8):
        t = _long16(); old_end = t['end_bar']
        info = TS.apply_one(t, 1.0, cap=cap)
        assert info['changed']
        assert t['end_bar'] < t1['end_bar'], (cap, t['end_bar'], t1['end_bar'])
        xs = np.array(t['xfader'])
        g_end = float(TE._db(np.interp(old_end, xs[:, 0], xs[:, 1])))
        assert g_end > -24 + 1e-6, (cap, g_end)  # outgoing still audible at the old window end
    assert i1['extended_by'] > 8


def test_gate_end_leaves_32_bar_solo_alone():
    t = _long32_solo(); old = [list(p) for p in t['xfader']]; end0 = t['end_bar']
    assert not TS.gate_end(t)
    info = TS.apply_one(t, 1.0, cap=4, gate='end')
    assert info['gated_out'] and not info['changed']
    assert t['xfader'] == old and t['end_bar'] == end0


def test_gate_end_fires_on_16_bar():
    t = _long16()
    assert TS.gate_end(t)
    info = TS.apply_one(t, 1.0, cap=4, gate='end')
    assert not info['gated_out'] and info['changed'] and info['cap'] == 4


def test_no_cap_no_gate_is_unchanged_behaviour():
    for name, X, f, sw in E._cases():
        a = E._trans(X, f, sw); b = E._trans(X, f, sw)
        ia = TS.apply_one(a, 1.0); ib = TS.apply_one(b, 1.0, cap=None, gate=None)
        assert a['xfader'] == b['xfader'] and a['end_bar'] == b['end_bar'] and ia == ib


def test_apply_respects_next_blend():
    t0 = _long16(); nxt = dict(a='B', b='C', start_bar=t0['end_bar'] + 2, end_bar=t0['end_bar'] + 18,
                               xfader=[[t0['end_bar'] + 2, 0.0], [t0['end_bar'] + 18, 1.0]])
    decks = [dict(id='A', start_bar=-10, end_bar=t0['end_bar'], full_map=[[k, 'n'] for k in range(26)], map=[]),
             dict(id='B', start_bar=0, end_bar=t0['end_bar'] + 18, full_map=[[k, 'n'] for k in range(34)], map=[]),
             dict(id='C', start_bar=t0['end_bar'] + 2, end_bar=t0['end_bar'] + 40, full_map=[[k, 'n'] for k in range(38)], map=[])]
    TS.apply(decks, [t0, nxt], 1.0, cap=8, gate='end', skip={'B'})
    assert t0['end_bar'] <= nxt['start_bar'] + 1e-9
    assert t0['xfader'][-1][1] == 1.0


def test_off_by_default():
    src = open(os.path.join(HERE, '..', '..', 'src2', 'mix_simple.py')).read()
    assert "_ts_cap=float(os.environ.get('TAIL_SHALLOW_CAP',0) or 0) or None" in src
    assert "_ts_gate=os.environ.get('TAIL_SHALLOW_GATE','') or None" in src
    # only reached inside the TAIL_SHALLOW>0 branch
    i = src.index("TS=float(os.environ.get('TAIL_SHALLOW',0) or 0)")
    assert src.index('_ts_cap=') > i
    rules = json.load(open(os.path.join(HERE, '..', '..', 'protrans', 'rules.json')))
    for k in ('TAIL_SHALLOW', 'TAIL_SHALLOW_CAP', 'TAIL_SHALLOW_GATE'):
        assert k not in rules
