"""FADE=long (2026-11-11 long-blend RCA, Shine In > Dusk To Dawn): early-in plateau + decisive outgoing exit on a phrase,
still one monotonic equal-power crossfader inside the X1 / abrupt-fade guards."""
import os, sys
import numpy as np
import pytest
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
sys.path.insert(0, os.path.join(ROOT, 'src2'))
import fade_long as FL

CASES = [(X, solo, xp) for X in (16, 32) for solo in (0, 8, 16) for xp in (0.3, 0.35)]


def _logged(X, **kw):
    """the crossfader as mix_simple logs it (one point per beat) and the guards read it (1/16 bar interpolation)"""
    xs = [(k / 4, FL.xlong(k / (4 * X), X, **kw) if k < 4 * X else 1.0) for k in range(4 * X + 1)]
    bars = np.arange(0, X + 1e-9, 1 / 16)
    x = np.interp(bars, [p[0] for p in xs], [p[1] for p in xs])
    return xs, bars, x


@pytest.mark.parametrize('X,solo,xp', CASES)
def test_single_monotonic_crossfader_within_x1(X, solo, xp):
    xs, bars, x = _logged(X, solo=solo, xp=xp)
    v = [p[1] for p in xs]
    assert v[0] == 0 and v[-1] == 1 and all(b >= a - 1e-12 for a, b in zip(v, v[1:]))
    for g in (np.cos(x * np.pi / 2), np.sin(x * np.pi / 2)):   # guardrail X1: <= 3 dB per beat above the -24 dB floor
        db = np.maximum(20 * np.log10(np.maximum(g, 1e-6)), -24)
        assert np.abs(db[4:] - db[:-4]).max() <= 3.0 + 1e-6


@pytest.mark.parametrize('X,solo,xp', CASES)
def test_outgoing_exit_is_gradual_and_lands_on_a_phrase(X, solo, xp):
    _, bars, x = _logged(X, solo=solo, xp=xp)
    ga = 20 * np.log10(np.cos(np.interp(np.arange(0, X + 1), bars, x) * np.pi / 2) + 1e-9)
    d = np.diff(ga)
    assert not [float(s) for s, v in zip(d, ga[1:]) if v > -24 and s < -3], ga   # test_outgoing_fader_tail_is_gradual rule
    ex = int(FL.exit_bar(X, solo=solo))
    assert ex % 4 == 0 and ga[ex] < -100 and ga[ex - 1] > -24        # decisive: out on a 4-bar boundary, not left at -30 dB
    assert ex == (X if X == 16 else X - solo)


@pytest.mark.parametrize('X,solo,xp', CASES)
def test_incoming_is_really_in_early(X, solo, xp):
    """the RCA gap: lin/tail kept the incoming under -12 dB for ~5 (lin) to 13 bars of a 32-bar window"""
    _, bars, x = _logged(X, solo=solo, xp=xp)
    gb = 20 * np.log10(np.sin(np.interp(np.arange(0, X + 1), bars, x) * np.pi / 2) + 1e-9)
    assert gb[2] >= -7 and (gb[2:int(FL.exit_bar(X, solo=solo))] >= -7).all()
    both = sum(1 for k in range(X) if gb[k] > -12 and 20 * np.log10(np.cos(np.interp(k, bars, x) * np.pi / 2) + 1e-9) > -12)
    assert both >= FL.exit_bar(X, solo=solo) - 6
    half = X // 4 + 1   # first quarter of the window: incoming far louder than the linear fade
    lin = 20 * np.log10(np.sin(np.arange(1, half) / X * np.pi / 2))
    assert float(np.mean(gb[1:half] - lin)) >= 4


@pytest.mark.parametrize('X,solo', [(16, 0), (32, 0), (32, 16)])
def test_bass_swap_has_room_on_the_plateau(X, solo):
    """the bass swap centre must sit at crossfader x 0.2-0.65 (guardrail X1): the plateau gives >= 4 bars of that"""
    _, bars, x = _logged(X, solo=solo)
    ok = [b for b, v in zip(bars, x) if 0.2 <= v <= 0.65]
    assert ok and ok[-1] - ok[0] >= 4


def test_lin_is_unchanged_when_fade_is_not_long():
    """FADE=lin/tail code path untouched: _xpos only branches to fade_long for FADE=long"""
    src = open(os.path.join(ROOT, 'src2', 'mix_simple.py')).read()
    body = src[src.index('def _xpos(u):'):].split('\ndef ', 1)[0]
    assert "if FADE=='long':return _FL.xlong(u,X,**LG)" in body and "if FADE=='lin' or u>=1:return u" in body


def test_struct_solo_ends_exit_on_the_outgoing_energy_drop():
    """LONG_SOLO_STRUCT: Shine In-like outgoing, full drop to bar 232 then -6 dB outro; window 208-240 -> exit ends at 232"""
    al = np.full(249, -18.0); al[232:] = -24.0; wa = list(range(208, 240))
    assert FL.struct_solo(al, wa, 32, solo=16) == 8
    assert FL.exit_bar(32, solo=FL.struct_solo(al, wa, 32, solo=16)) == 24


def test_struct_solo_falls_back_and_never_squeezes_the_plateau():
    al = np.full(249, -18.0); wa = list(range(208, 240))
    assert FL.struct_solo(al, wa, 32, solo=16) == 16                 # no energy drop in the window: fixed LONG_SOLO
    al[212:] = -30.0                                                 # a drop before rise+exit+4 bars is ignored
    assert FL.struct_solo(al, wa, 32, solo=16) == 32 - 16
    assert FL.struct_solo(np.full(100, -18.0), list(range(80, 96)), 16, solo=0) == 0


@pytest.mark.parametrize('X,solo', [(16, 0), (32, 0), (32, 8), (32, 16)])
def test_long_swap_exit_is_inside_x1_swap_window(X, solo):
    """LONG_SWAP=exit: swap centred on the exit start, where x = xp2 (inside X1's 0.2-0.65)"""
    p = FL.swap_pos(X, solo=solo); c = p * X
    assert c == FL.exit_start(X, solo=solo)
    assert 0.2 <= FL.xlong(c / X, X, solo=solo) <= 0.65
