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

def test_cap_solo_incoming_zero_when_second_half_crashes():
  # Bad To Me / Solitude-style: first half at body, second half drops 12 dB (E1 / bass hole if we solo)
  al=np.r_[np.zeros(16),np.full(16,-12.)]; lo=al.copy(); wb=list(range(32))
  assert int(FL.cap_solo_incoming(al,lo,wb,32,solo=16))==0

def test_cap_solo_incoming_keeps_16_when_second_half_is_as_strong():
  # a uniformly slightly-quiet intro (Forest Fires trans 0) must not delay the exit — that layered vocals
  al=np.full(64,-7.); lo=al.copy(); wb=list(range(32))
  assert int(FL.cap_solo_incoming(al,lo,wb,32,solo=16))==16

def test_cap_solo_incoming_keeps_16_when_incoming_is_ready_at_16():
  al=np.r_[np.full(16,-40.),np.zeros(80)]; lo=al.copy(); wb=list(range(32))
  assert int(FL.cap_solo_incoming(al,lo,wb,32,solo=16))==16

def test_vocal_hold_leading_clash():
  vA=np.full(32,-100.);vB=np.full(32,-100.);vA[2:5]=0;vB[2:5]=0
  wa=wb=list(range(32))
  assert FL.vocal_hold(vA,0,wa,vB,0,wb,32)==5
  vB2=np.full(32,-100.);assert FL.vocal_hold(vA,0,wa,vB2,0,wb,32)==0
  # a weak first bar then a 1-bar gap must not hide the real phrase (Mix 08 long1c trans 22)
  vA=np.full(32,-100.);vB=np.full(32,-100.);vA[0]=0;vB[0]=0;vA[2:5]=0;vB[2:5]=0
  assert FL.vocal_hold(vA,0,wa,vB,0,wb,32)==5

def test_xlong_hold_stays_zero_then_rises_monotonic():
  xs=[FL.xlong(b/32,32,hold=3,solo=16) for b in np.arange(0,32.01,0.25)]
  assert all(x==0 for x in xs[:12])  # 3 bars * 4 beats
  assert all(a<=b+1e-9 for a,b in zip(xs,xs[1:])) and xs[-1]==1


def _phrase_snap_cands(X, SW=4, **kw):
  """the tail planner's beat-on-beat candidates (mix_simple.swap_at range(4,X,4) with x at the centre)."""
  return [c for c in range(4, X, 4) if 0.2 <= FL.xlong((c + SW / 2) / X, X, **kw) <= 0.65]

def test_long_swap_legal_when_phrase_snap_is_empty():
  """Mix 08 long1b (2026-11-11): a 16-bar long fade with a 6-bar vocal hold and a 4-bar bass swap left
  the tail phrase-snap with no bar in x 0.2-0.65. LONG_SWAP=exit must still return a legal centre."""
  kw=dict(hold=6, solo=0, rise=2, exit_=8)
  assert _phrase_snap_cands(16, 4, **kw) == []
  pos=FL.swap_pos(16, **kw)
  assert 0.2 <= FL.xlong(pos, 16, **kw) <= 0.65

def test_swap_pos_matches_xlong_exit_start_with_hold():
  for X,hold,solo in ((16,0,0),(16,6,0),(32,0,16),(32,6,16),(32,0,0)):
    kw=dict(hold=hold,solo=solo,rise=2,exit_=8)
    pos=FL.swap_pos(X,**kw); ex=FL.exit_start(X,**kw)
    assert abs(pos*X-ex)<1e-9
    assert abs(FL.xlong(pos,X,**kw)-0.5)<1e-9  # xp2: still in X1's 0.2-0.65 window

def test_swap_pos_in_x1_window_on_typical_long_blends():
  for X,hold,solo in ((16,0,0),(16,3,0),(16,6,0),(32,0,16),(32,6,16),(32,0,0),(32,8,0)):
    x=FL.xlong(FL.swap_pos(X,hold=hold,solo=solo),X,hold=hold,solo=solo)
    assert 0.2<=x<=0.65, (X,hold,solo,x)


def test_solo_before_incoming_vocal_exits_before_a_late_vocal():
  # cap_solo had delayed the exit to the window end (solo=0); incoming sings at bar 25
  vB=np.full(32,-100.);vB[25]=0;wb=list(range(32))
  s=FL.solo_before_incoming_vocal(vB,0,wb,32,solo=0,hold=0)
  assert s>=4
  x=FL.xlong(25/32,32,solo=s)
  assert np.cos(x*np.pi/2)<=0.3+1e-9

def test_solo_before_incoming_vocal_leaves_an_early_exit_alone():
  vB=np.full(32,-100.);vB[25]=0;wb=list(range(32))
  assert int(FL.solo_before_incoming_vocal(vB,0,wb,32,solo=16,hold=0))==16

def test_solo_before_incoming_vocal_ignores_leading_clashes():
  # bars 2-4 are vocal_hold's job; must not force an early exit
  vB=np.full(32,-100.);vB[2:5]=0;wb=list(range(32))
  assert int(FL.solo_before_incoming_vocal(vB,0,wb,32,solo=16,hold=5))==16


def test_vocal_exit_params_lengthens_exit_when_cap_blocks_solo():
  # long1e trans 18 shape: cap_solo=0 to cover a late thin stretch; incoming sings at bar 25.
  # Must not raise solo (that re-opened the 1901 bass gap). Lengthen the exit instead.
  vB=np.full(32,-100.);vB[25]=0;wb=list(range(32))
  s,ex=FL.vocal_exit_params(vB,0,wb,32,solo=0,hold=0,cap_solo=0)
  assert s==0
  assert ex>8
  x=FL.xlong(25/32,32,solo=s,exit_=ex)
  assert np.cos(x*np.pi/2)<=0.3+1e-9
  # still present through a thin bar at +30 (1901-ish on a 1872-1904 window)
  assert FL.xlong(30/32,32,solo=s,exit_=ex)<1-1e-6
  # longer exit is shallower than 3 dB/bar (linear in dB from -3 to -24)
  a0=20*np.log10(np.cos(0.5*np.pi/2)); assert (-24-a0)/ex<=3+1e-9

def test_vocal_exit_params_can_still_raise_solo_when_uncapped():
  vB=np.full(32,-100.);vB[25]=0;wb=list(range(32))
  s,ex=FL.vocal_exit_params(vB,0,wb,32,solo=0,hold=0,cap_solo=None)
  assert s>=4 and ex==8

def test_bass_lead_long_outgoing_leaves_first():
  assert FL.bass_lead(1.0,fade='long')==(1.0,0.0)
  assert FL.bass_lead(1.0,fade='tail')==(0.5,0.5)
  assert FL.bass_lead(1.0,phrase=True,fade='tail')==(1.0,0.0)

def test_long_swap_centre_still_in_x1_with_outgoing_lead():
  # centre stays at exit start, x=0.5, even though the outgoing lane starts one bar earlier
  X=32; pos=FL.swap_pos(X,solo=16)
  x=FL.xlong(pos,X,solo=16)
  assert 0.2<=x<=0.65
  # a 2-bar swap starting at the exit would centre at exit+1, still legal, but we do not use it
  # (long1 Ember abrupt tail). Document the x at exit+1 stays <=0.65.
  ex0=FL.exit_start(X,solo=16)
  x1=FL.xlong((ex0+1)/X,X,solo=16)
  assert x1<=0.65+1e-9
