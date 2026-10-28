"""What made Mix 02 good, as tests (MIX2_VS_MIX3.md, 2026-10-28). Each threshold is set so that Mix 02 (mix2b) passes
and the measured failure in old Mix 03 (mix360f) or mixT is caught. The long-lull trait is guardrail E4 (audio-based)."""
import os,json,sys,numpy as np,pytest
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import checks as C
pytestmark=pytest.mark.skipif(not os.path.exists(f'{C.SRC}/{C.NAME}_meta.json'),reason='mix meta missing')
def body_coverage(d):
  """share of the record's loud bars (>= body-6 dB, body = 75th pct bar level) that the mix actually plays"""
  al=C.src_bars(d['id']);loud=set(np.where(al>np.percentile(al,75)-6)[0].tolist())
  return len(loud&{s for s,_ in d['full_map']})/max(1,len(loud))
def test_each_track_gets_its_body():
  """Mix 02 played 86% of each record's loud body on average; mixT dropped to 74% with Always Be at 34% and Strings Of Life at 47%."""
  cov={d['id']:round(body_coverage(d),2) for d in C.decks() if not d.get('acap')}
  assert np.mean(list(cov.values()))>=0.8 and min(cov.values())>=0.5,cov
def test_blends_mostly_32_bars():
  """Mix 02: 10 of 12 blends overlap >= 32 bars. Long beat-through blends are its signature; 16 is the fallback, not the norm."""
  M=C.meta();n=[t['end_bar']-t['start_bar'] for t in M['trans'] if 'echo' not in t['tech']]
  assert sum(x>=32 for x in n)>=len(n)/2,n
def test_no_long_drums_only_stretch():
  """Old Mix 03 ran 12-14 bar drums-only stem loops (22:57-25:18); Mix 02 never exceeded 4 bars. Fail at >= 8 bars where every
  audible deck plays drums only (a drums stem, or a source bar whose full mix is within 2 dB of its drums)."""
  M=C.meta();D=M['decks'];NB=max(d['end_bar'] for d in D);run=worst=0;at=None
  info={d['id']:json.load(open(f"{C.SRC}/st/{d['id']}.json"))['bar'] for d in D}
  for j in range(NB):
    aud=[]
    for d in D:
      if not d['start_bar']<=j<d['end_bar']:continue
      g=C.gain_at(d,'gain',j+.5) if d['auto'].get('gain') else 1.0
      if d['auto'].get('mid') or d['auto'].get('high'):g*=max(C.gain_at(d,'mid',j+.5),C.gain_at(d,'high',j+.5))
      if g>0.3:aud.append(d)
    def dr(d):
      s,lab=C.src_of(d,j);b=info[d['id']]
      return lab=='drums' or (s<len(b['all']) and b['all'][s]-b['drums'][s]<2.0)
    run=run+1 if aud and all(dr(d) for d in aud) else 0
    if run>worst:worst,at=run,j
  assert worst<8,f'{worst} drums-only bars ending {int(at*M["bar_sec"]//60)}:{int(at*M["bar_sec"]%60):02d}'
