"""Bass swap and optional high swap (HIGH_SWAP, >2 kHz lane) checks on the rendered decks (each deck alone, crossfader + low-band lane applied, same engine):
no doubled bass outside the 2-bar swap, phrase-snapped swaps (SWAP_PHRASE) centred on a 4-bar boundary, no level dip at the swap."""
import os,sys,functools,numpy as np,pytest
from scipy.signal import butter,sosfiltfilt
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import checks as C,deckpair as P
pytestmark=pytest.mark.skipif(not os.path.exists(f'{C.SRC}/{C.NAME}_meta.json'),reason='mix meta missing')
LP=butter(4,150,'low',fs=P.SR,output='sos');HP=butter(4,2000,'high',fs=P.SR,output='sos');BAR=P.BAR;SR=P.SR
DOUBLE_DB=6;DOUBLE_MAX=2;DIP_DB=3
def _db(x):return 10*np.log10(np.mean(x**2)+1e-12)
@functools.lru_cache()
def blends():
  """per swap blend: per-bar low-band dB of each deck and per-beat full-band dB of their sum, around the blend"""
  M=P.meta();D=M['decks'];out=[]
  for t in M['trans']:
    if not t.get('bass_swap'):continue
    A=[d for d in D if d['id']==t['a'] and d['start_bar']<t['start_bar']+1 and not d.get('acap')][-1]
    B=[d for d in D if d['id']==t['b'] and abs(d['start_bar']-t['start_bar'])<1e-6][0]
    s,e=int(t['start_bar']),int(t['end_bar']);ya,yb=P._render(A),P._render(B)
    cut=lambda d,y:y[int((s-d['start_bar'])*BAR*SR):int((e-d['start_bar'])*BAR*SR)]
    a,b=cut(A,ya),cut(B,yb);n=min(len(a),len(b));a,b=a[:n],b[:n];la,lb,ha,hb=sosfiltfilt(LP,a),sosfiltfilt(LP,b),sosfiltfilt(HP,a),sosfiltfilt(HP,b);L=int(BAR*SR)
    bars=[(_db(la[k*L:(k+1)*L]),_db(lb[k*L:(k+1)*L])) for k in range(n//L)];hbars=[(_db(ha[k*L:(k+1)*L]),_db(hb[k*L:(k+1)*L])) for k in range(n//L)];m=a+b;Q=L//4
    out.append(dict(t=t,s=s,bars=bars,hbars=hbars,beats=[_db(m[k*Q:(k+1)*Q]) for k in range(n//Q)]))
  return out
def _doubled(B):
  ref=max(max(x) for x in B);return sum(min(x)>ref-12 and abs(x[0]-x[1])<DOUBLE_DB for x in B)
def test_bass_never_doubles():
  """Both decks' low bands loud and within 6 dB of each other for at most 2 blend bars (the swap itself)."""
  bad=[]
  for r in blends():
    k=_doubled(r['bars'])
    if k>DOUBLE_MAX:bad.append((C.ts(r['s']*BAR) if hasattr(C,'ts') else round(r['s']*BAR/60,2),r['t']['a'],r['t']['b'],k))
  assert not bad,bad
def test_phrase_swaps_land_on_phrase_boundary():
  T=[t for t in P.meta()['trans'] if t.get('swap_phrase')]
  if not T:pytest.skip('no phrase-snapped swaps in this mix')
  assert all((t['swap_bar']-t['start_bar'])%4==0 for t in T),[(t['a'],t['swap_bar']-t['start_bar']) for t in T if (t['swap_bar']-t['start_bar'])%4]
def test_no_level_dip_at_swap():
  """Summed decks over each swap (bass, and high when present) (+-1 bar, per half bar so a single drum-fill beat doesn't count) stay within 3 dB of the quieter of the 2 bars before and after."""
  bad=[]
  for r in blends():
    bt=np.array(r['beats'])
    for sb in (r['t']['swap_bar'],r['t'].get('high_bar')):
      if sb is None:continue
      c=int(round((sb-r['s'])*4))
      if c-12<0 or c+12>len(bt):continue
      ref=min(np.mean(bt[c-12:c-4]),np.mean(bt[c+4:c+12]));lo=float(min(np.mean(bt[j:j+2]) for j in range(c-4,c+4,2)))
      if lo<ref-DIP_DB:bad.append((round(r['s']*BAR/60,2),r['t']['a'],r['t']['b'],sb-r['s'],round(lo-ref,1)))
  assert not bad,bad
def test_eq_lanes_monotonic_in_every_blend():
  """Inside each blend the outgoing deck's low/high lanes only fall and the incoming deck's only rise."""
  M=P.meta();bad=[]
  for t in M['trans']:
    bb=np.arange(t['start_bar'],t['end_bar']+1e-9,1/16)
    for d in M['decks']:
      if d['id'] not in (t['a'],t['b']) or d['end_bar']<=t['start_bar'] or d['start_bar']>=t['end_bar']:continue
      for lane in ('low','high'):
        v=d['auto'].get(lane)
        if not v:continue
        dl=np.diff(np.interp(bb,[p[0] for p in v],[p[1] for p in v]))
        if (dl<-1e-6).any() if d['id']==t['b'] else (dl>1e-6).any():bad.append((t['a'],t['b'],d['id'],lane))
  assert not bad,bad
def test_high_swaps_on_phrase_apart_from_bass():
  T=[t for t in P.meta()['trans'] if t.get('high_bar') is not None]
  if not T:pytest.skip('no high swaps in this mix')
  bad=[(t['a'],t['high_bar']-t['start_bar'],t['swap_bar']-t['start_bar']) for t in T if (t['high_bar']-t['start_bar'])%4 or abs(t['high_bar']-t['swap_bar'])<4]
  assert not bad,bad
def test_high_swap_no_doubled_highs():
  """With a high swap, both decks' >2 kHz bands loud and within 6 dB for at most 2 blend bars (no stacked hats/air)."""
  R=[r for r in blends() if r['t'].get('high_bar') is not None]
  if not R:pytest.skip('no high swaps in this mix')
  bad=[(round(r['s']*BAR/60,2),r['t']['a'],r['t']['b'],_doubled(r['hbars'])) for r in R if _doubled(r['hbars'])>DOUBLE_MAX]
  assert not bad,bad
