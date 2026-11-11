"""2026-11-11: the outgoing 'ride after the bass swap' rule is calibrated to pro p95 (src/calib/ride_vs_pro.py)."""
import json,os,sys,re
import numpy as np
R0='/workspace/mixes';sys.path.insert(0,f'{R0}/src/calib');sys.path.insert(0,f'{R0}/src2')
import ride_vs_pro as RV, fade_long as F
TEST=f'{R0}/src/build_qa/test_release_structure_tail.py'
def _frac():return float(re.search(r'^RIDE_FRAC=([0-9.]+)',open(TEST).read(),re.M).group(1))

def test_ride_metric_counts_like_the_test():
  o=np.r_[np.zeros(20),np.full(4,-22.),np.full(6,-60.)];i=np.r_[np.full(4,-40.),np.zeros(26)]
  m=RV.ride_metric(o,i,10)
  assert (m['start'],m['end'],m['X'],m['ride'])==(4,24,20,10) and not m['fail']
  m=RV.ride_metric(o,i,19);assert m['ride']==1 and m['fail']  # need 0.35*20-1=6
def test_ride_metric_none_without_swap_or_entry():
  assert RV.ride_metric(np.zeros(10),np.zeros(10),None) is None
  assert RV.ride_metric(np.zeros(10),np.full(10,-60.),3) is None
def test_frac_is_pro_p5_not_hand_set():
  d=json.load(open(f'{R0}/src/calib/ride_vs_pro_results.json'));p5=d['summary']['pass_frac']['p5']
  assert d['summary']['n_measured']>=30 and abs(_frac()-round(p5,2))<1e-9
def test_frac_not_below_measured_pro_p5():
  d=json.load(open(f'{R0}/src/calib/ride_vs_pro_results.json'))
  assert _frac()>=round(d['summary']['pass_frac']['p5'],2)-1e-9 and _frac()<=0.35
def _ride(X,solo,swap_bars=3):
  bars=np.arange(0,X+1e-9,1.0);x=np.array([F.xlong(b/X,X,solo=solo) for b in bars]);g=20*np.log10(np.cos(x*np.pi/2)+1e-9)
  sw=F.exit_start(X,solo=solo)+swap_bars/2  # the test reads the END of the bass swap, centred on the exit start
  return float(np.sum(g[bars>=sw]>-20))
def test_fade_long_32_bar_window_passes_calibrated_ride():
  for solo in (16,8):assert _ride(32,solo)>=_frac()*32-1
def test_fade_long_32_bar_window_failed_old_rule():
  assert _ride(32,16)<0.35*32-1  # why FADE=long was blocked: ~6 bars vs 10.2 needed
