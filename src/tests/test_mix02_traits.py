"""What made Mix 02 good, as tests (MIX_REFERENCE.md, 2026-10-28). Each threshold is set so that Mix 02 (mix2b) passes
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

def _drum_runs():
  """per blend: (longest straight run of bars where BOTH decks play drums, bars where NEITHER deck plays drums, overlap bars).
  A deck 'drums' in a bar when its source bar's drum stem is within 8 dB of that record's drum body (75th pct)."""
  M=C.meta();D=M['decks'];info={}
  def on(d,j):
    if d['id'] not in info:
      b=np.array(json.load(open(f"{C.SRC}/st/{d['id']}.json"))['bar']['drums']);info[d['id']]=b>np.percentile(b,75)-8
    s,lab=C.src_of(d,j);b=info[d['id']]
    return lab=='drums' or (s is not None and 0<=s<len(b) and bool(b[s]))
  out=[]
  for t in M['trans']:
    if 'echo' in t['tech']:continue
    run=best=none=0;n=int(t['end_bar']-t['start_bar'])
    for j in range(int(t['start_bar']),int(t['end_bar'])):
      on_=[on(d,j) for d in D if d['id'] in(t['a'],t['b']) and d['start_bar']<=j<d['end_bar'] and not d.get('acap')]
      both=len(on_)>=2 and all(on_);run=run+1 if both else 0;best=max(best,run);none+=not any(on_)
    out.append((best,none,n))
  return out
def test_half_the_blends_beat_on_beat_16_bars():
  """Mix 02: 7/12 blends have 16+ straight bars with both decks drumming. the listener wants more beat-on-beat, so >= half."""
  r=_drum_runs();assert sum(b>=16 for b,_,_ in r)>=len(r)/2,r
def test_few_beatless_blends():
  """At most 1 in 3 blends may be mostly beatless (neither deck drumming in over half its bars)."""
  r=_drum_runs();assert sum(nn>n/2 for _,nn,n in r)<=len(r)/3,r
