"""engine.nudge / st/<id>.nudge.json is milliseconds on those source bars only.

The alignment checker (checks.nudge_ms) must apply the same sidecar. A missing
sidecar made a 19 ms intro offset show up as |lag_0| > 10 ms, with the wide
phase search then reporting a 2- or 4-beat DnB alias.
"""
import os,sys
import numpy as np
import pytest

HERE=os.path.dirname(os.path.abspath(__file__))
SRC2=os.path.join(HERE,'..','..','src2')
sys.path.insert(0,SRC2)
import engine as E

WML='7Itbo72XEz4'
INTRO_BAR=20   # inside the sidecar range 15-27
DROP_BAR=32    # outside it; must not move
NUDGE_MS=19.1
BEAT=60/174.0
SR=44100

def _wml_sidecar_present():
  return os.path.exists(os.path.join(SRC2,'st',f'{WML}.nudge.json')) and \
         os.path.exists(os.path.join(SRC2,'st',f'{WML}.wav'))

def _xcorr_lag_ms(ref, sig, sr=SR, lim_ms=80):
  """Lag of sig behind ref, in ms. Positive = sig is delayed vs ref."""
  a=np.asarray(ref,float).mean(1) if np.asarray(ref).ndim==2 else np.asarray(ref,float)
  b=np.asarray(sig,float).mean(1) if np.asarray(sig).ndim==2 else np.asarray(sig,float)
  n=min(len(a),len(b));a,b=a[:n]-a[:n].mean(),b[:n]-b[:n].mean()
  if a.std()==0 or b.std()==0:return None
  c=np.correlate(b,a,mode='full');mid=n-1
  lim=int(round(lim_ms/1000*sr));sl=c[mid-lim:mid+lim+1]
  return (int(np.argmax(sl))-lim)/sr*1000

@pytest.fixture
def in_src2():
  cwd=os.getcwd();os.chdir(SRC2)
  try:yield
  finally:os.chdir(cwd)

def test_sidecar_units_are_milliseconds_and_bar_scoped(in_src2):
  if not _wml_sidecar_present():
    pytest.skip('When My Love source or sidecar not on this box')
  E._TRACK_NUDGE.clear()
  tr=E.track(WML)
  intro=E.nudge(tr,INTRO_BAR)
  drop=E.nudge(tr,DROP_BAR)
  # milliseconds, not seconds or bars: 19.1, not 19.1*1000 or 19.1*BAR
  assert abs(intro-NUDGE_MS)<0.6, intro
  assert abs(drop)<0.6, drop  # drop phrase is not moved
  # the read-head math is ms/1000, not seconds-as-written or bars
  j_plain=int(round((tr['d0']+INTRO_BAR*E.BAR)*E.SR))
  j_nudged=int(round((tr['d0']+INTRO_BAR*E.BAR-E.nudge(tr,INTRO_BAR)/1000)*E.SR))
  shift_ms=(j_plain-j_nudged)/E.SR*1000
  assert abs(shift_ms-NUDGE_MS)<0.6, shift_ms
  assert abs(shift_ms-NUDGE_MS*1000)>1000
  assert abs(shift_ms-NUDGE_MS*E.BAR)>1

def test_positive_nudge_delays_those_bars_by_that_many_ms_not_beats(in_src2):
  if not _wml_sidecar_present():
    pytest.skip('When My Love source or sidecar not on this box')
  tr=E.track(WML)
  n=int(round(E.BS))
  orig=E.nudge
  try:
    E.nudge=lambda tr,k:0
    y0=E._bars(tr,[INTRO_BAR],tr['st']['mix'],n)
    E.nudge=lambda tr,k:NUDGE_MS
    y1=E._bars(tr,[INTRO_BAR],tr['st']['mix'],n)
  finally:
    E.nudge=orig
  lag= _xcorr_lag_ms(y0,y1)
  assert lag is not None
  # positive nudge = read earlier = hits land later. Units are ms, not beats (~345 ms) or seconds.
  assert abs(lag-NUDGE_MS)<2.0, lag
  assert abs(lag-BEAT*1000)>100
  assert abs(lag-2*BEAT*1000)>100
  assert abs(lag-NUDGE_MS*1000)>1000
  # applying the same value to a bar with no planned sidecar must still be a *bar*
  # offset (the function is per-bar); the drop is not in the sidecar, so the
  # real engine.nudge for the drop is ~0 — checked in the units test. Here we
  # only show that a whole-track mis-apply would have moved the drop too: the
  # sidecar file itself does not list it.
  drop_sidecar=E._track_nudge(WML).get(str(DROP_BAR),0)
  assert drop_sidecar==0

def test_alignment_checker_uses_the_same_sidecar(in_src2):
  if not _wml_sidecar_present():
    pytest.skip('When My Love source or sidecar not on this box')
  # checks is configured via MIX_SRC; default is already src2
  os.environ.setdefault('MIX_SRC',SRC2)
  import checks as C
  C._TRACK_NUDGE.clear()
  if hasattr(C._nudges,'cache_clear'):C._nudges.cache_clear()
  E._TRACK_NUDGE.clear()
  tr=E.track(WML)
  for k in (15,16,20,27,28,32):
    assert abs(C.nudge_ms(WML,k)-E.nudge(tr,k))<1e-9, (k,C.nudge_ms(WML,k),E.nudge(tr,k))
