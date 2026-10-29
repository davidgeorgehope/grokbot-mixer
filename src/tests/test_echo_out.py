"""Delay-tail exits (ECHO_OUT): each outgoing deck with d['echo_out'] is re-rendered alone (same engine) and its wet tail
(audio past the deck's crossfader end) checked against the incoming deck: on the phrase boundary, low-cut clear of the
incoming kick/bass, no >3 dB level jump from the tail, below -40 dB within 4 bars, dry deck unchanged by the option."""
import os,sys,functools,numpy as np,pytest
from scipy.signal import butter,sosfiltfilt
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import checks as C,deckpair as P
pytestmark=pytest.mark.skipif(not os.path.exists(f'{C.SRC}/{C.NAME}_meta.json'),reason='mix meta missing')
SR=P.SR;BAR=P.BAR;L=int(round(BAR*SR));LP=butter(4,150,'low',fs=SR,output='sos')
def _db(x):return 10*np.log10(np.mean(x**2)+1e-12)
@functools.lru_cache()
def tails():
  M=P.meta();D=M['decks'];out=[]
  for t in M['trans']:
    if not t.get('echo_out'):continue
    A=[d for d in D if d['id']==t['a'] and abs(d['end_bar']-t['end_bar'])<1e-6][0];B=[d for d in D if d['id']==t['b'] and abs(d['start_bar']-t['start_bar'])<1e-6][0]
    ya,yb=P._render(A),P._render(B);n=int(round((A['end_bar']-A['start_bar'])*BAR*SR));e=int(round((t['end_bar']-B['start_bar'])*BAR*SR))
    dry=P._render({k:v for k,v in A.items() if k!='echo_out'})
    out.append(dict(t=t,A=A,tail=ya[n:],dryA=dry,ya=ya[:n],b=yb[e-2*L:e+4*L],n=n))
  return out
def _need():
  if not tails():pytest.skip('no delay-tail exits in this mix')
def test_echo_tail_lands_on_phrase_boundary():
  """the tail starts exactly at the outgoing crossfader end, which is a 4-bar boundary of the blend, and is loudest in its first bar"""
  _need();bad=[]
  for r in tails():
    t=r['t'];bars=[_db(r['tail'][k*L:(k+1)*L]) for k in range(len(r['tail'])//L)]
    if (t['end_bar']-t['start_bar'])%4 or abs(r['A']['end_bar']-t['end_bar'])>1e-6 or int(np.argmax(bars)):bad.append((t['a'],t['end_bar'],[round(x,1) for x in bars]))
  assert not bad,bad
def test_echo_tail_clear_of_incoming_kick():
  """tail <150 Hz at least 24 dB under the incoming deck's <150 Hz in the first tail bar (low-cut: no doubled kick/bass)"""
  _need();bad=[]
  for r in tails():
    tl=_db(sosfiltfilt(LP,r['tail'][:L]));bl=_db(sosfiltfilt(LP,r['b'][2*L:3*L]))
    if tl>bl-24:bad.append((r['t']['a'],round(tl,1),round(bl,1)))
  assert not bad,bad
def test_echo_tail_no_level_jump():
  """incoming + tail vs incoming alone, per half bar over the 4 tail bars: never more than 3 dB louder or quieter"""
  _need();bad=[];H=L//2
  for r in tails():
    b=r['b'][2*L:];x=b[:len(r['tail'])]+r['tail'][:len(b)]
    d=[_db(x[k*H:(k+1)*H])-_db(b[k*H:(k+1)*H]) for k in range(len(x)//H)]
    if max(abs(v) for v in d)>3:bad.append((r['t']['a'],[round(v,1) for v in d]))
  assert not bad,bad
def test_echo_tail_decays_within_4_bars():
  """the last beat of the tail is >=40 dB under its first beat and nothing plays after 4 bars"""
  _need();bad=[];Q=L//4
  for r in tails():
    t=r['tail'];first,last=_db(t[:Q]),_db(t[-Q:])
    if last>first-40 or len(t)>4*L+1:bad.append((r['t']['a'],round(first,1),round(last,1),len(t)/L))
  assert not bad,bad
def test_echo_out_leaves_dry_deck_identical():
  """off = identical: the option only appends the tail; the deck's own audio (crossfader, EQ lanes) is bit-identical"""
  _need();assert all(np.array_equal(r['ya'],r['dryA']) for r in tails())
