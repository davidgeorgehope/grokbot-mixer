"""'Ears' checks (ears.py), calibrated 2026-10-28 on mixLen21b against the listener's ratings:
Bad To Me -> Blame You 33:50 (1/5, 'beats clash') = 25 beat-off bars -> FAIL; Parallel -> Bad To Me 30:31 (5/5) = 2 -> PASS;
old Sweet Lies -> Supernova 14:42 ('a bit weird') = 13 -> FAIL. Chroma dissonance is reported per blend but does not gate:
it did not separate the 1/5 blend (p90 0.27) from the 5/5 one (0.31) in calibration."""
import os,sys,json,functools,numpy as np,pytest
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import checks as C,deckpair as P,ears as E
pytestmark=pytest.mark.skipif(not os.path.exists(f'{C.SRC}/{C.NAME}_meta.json'),reason='mix meta missing')
BEATOFF_TH=0.3;BEATOFF_MAX_BARS=8
@functools.lru_cache()
def _act(i):
  b=np.array(json.load(open(f"{C.SRC}/st/{i}.json"))['bar']['drums']);return b>np.percentile(b,75)-8
def _drums(d,j):
  s,lab=C.src_of(d,j);b=_act(d['id']);return lab=='drums' or (s is not None and 0<=s<len(b) and bool(b[s]))
@functools.lru_cache()
def scores():
  M=P.meta();D=M['decks'];out=[]
  for ti,t in enumerate(M['trans']):
    if 'echo' in t['tech']:continue
    ia=max(i for i,d in enumerate(D) if d['id']==t['a'] and d['start_bar']<t['start_bar']+1 and not d.get('acap'))
    ib=[i for i,d in enumerate(D) if d['id']==t['b'] and abs(d['start_bar']-t['start_bar'])<1e-6][0]
    A,B=D[ia],D[ib];s,e=int(t['start_bar']),int(t['end_bar'])
    g=lambda d:(lambda y:y[int((s-d['start_bar'])*E.BAR*E.SR):int((e-d['start_bar'])*E.BAR*E.SR)])(P._render(d))
    sa,sb=g(A),g(B);n=min(len(sa),len(sb));sa,sb=sa[:n],sb[:n]
    pa,pb=E.pattern(sa),E.pattern(sb)
    bo=[E.beat_off(pa[k],pb[k]) for k in range(min(len(pa),len(pb))) if _drums(A,s+k) and _drums(B,s+k)]  # only bars where both decks drum
    ca,cb=E.chroma_beats(sa),E.chroma_beats(sb);m=min(len(ca),len(cb));dis=[E.dissonance(ca[k],cb[k]) for k in range(m)]
    out.append(dict(t=C.ts(s*E.BAR) if hasattr(C,'ts') else round(s*E.BAR/60,2),a=t['a'],b=t['b'],beatoff_bars=int(sum(x>BEATOFF_TH for x in bo)),dis_p90=round(float(np.percentile(dis,90)),3) if dis else 0))
  json.dump(out,open(f'{C.SRC}/{C.NAME}_ears.json','w'),indent=1);return out
def test_backbeats_line_up_through_every_blend():
  """Kick/snare patterns of the two decks must line up bar by bar (not off by a beat or half-bar) for all but 8 blend bars."""
  bad=[(r['t'],r['a'],r['b'],r['beatoff_bars']) for r in scores() if r['beatoff_bars']>BEATOFF_MAX_BARS]
  assert not bad,bad
