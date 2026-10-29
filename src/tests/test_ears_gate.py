"""Ears gate: the GPU ears check (ears/ears.sh: demucs drums -> Beat This grids per deck) AND a direct drum check on the box must
both say a blend is off before it fails. Ears alone = 'suspect' (warning only).
Calibrated 2026-10-29 on the listener's ratings (ratings.jsonl): ears flagged 3 blends he heard, direct check said aligned on all 3:
  Mix 04 24:16 U & I -> Alone        ears FAIL, lag 1.5 ms, beat-off 2 bars -> rated 3.5 (false positive)
  Mix 03v2 2:57 Supernova -> Solitude ears FAIL, beat-off 1 bar             -> rated 3   ('a little weird': real but mild -> planner penalty, not a fail)
  Mix 03v2 51:52 When My Love -> Half Life ears FAIL, beat-off 4 bars       -> rated 4   (false positive)
The 1/5 blend (34:05 Bad To Me -> Blame You) had 21-25 beat-off bars, so the direct thresholds sit well between.
Writes <SRC>/<NAME>_ears_gate.json; src2/plan_search.py bans confirmed windows and penalises rated-mediocre suspects."""
import os,sys,json,subprocess,functools,warnings,numpy as np,librosa,pytest
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import checks as C,deckpair as P,ears as E,test_ears as TE
pytestmark=pytest.mark.skipif(not os.path.exists(f'{C.SRC}/{C.NAME}_meta.json'),reason='mix meta missing')
ROOT=os.path.abspath(os.path.join(os.path.dirname(__file__),'..','..'))
LAG_MS=20  # direct deck-vs-deck onset lag that counts as 'off'; aligned blends measure 0-1.5 ms
def _host():
  if os.environ.get('EARS_HOST'):return os.environ['EARS_HOST']
  for l in open(f'{ROOT}/config.env'):
    if l.strip().startswith('export HOST='):return l.split('=',1)[1].strip().strip('"\'')
def report():
  """ears report for this meta; re-run ears.sh on the GPU host when missing or older than the meta"""
  r,m=f'{ROOT}/ears/{C.NAME}_ears_report.json',f'{C.SRC}/{C.NAME}_meta.json'
  if not os.path.exists(r) or os.path.getmtime(r)<os.path.getmtime(m):
    N=os.environ.get('NUDGE','');N=[os.path.join(C.SRC,N)] if N and os.path.exists(os.path.join(C.SRC,N)) else []  # same warp nudges as the render
    subprocess.run(['bash',f'{ROOT}/ears/ears.sh',m,*N],check=True,env={**os.environ,'EARS_HOST':_host()},stdout=subprocess.DEVNULL)
  return json.load(open(r))
@functools.lru_cache()
def direct_lag(k):
  """median onset lag (ms) between the two decks, rendered alone, over the bars where both drum"""
  M=P.meta();t=M['trans'][k];D=M['decks']
  A=[d for d in D if d['id']==t['a'] and d['start_bar']<t['start_bar']+1 and not d.get('acap')][-1]
  B=[d for d in D if d['id']==t['b'] and abs(d['start_bar']-t['start_bar'])<1e-6][0]
  s,e=int(t['start_bar']),int(t['end_bar']);ya,yb=P._render(A),P._render(B);L=int(E.BAR*E.SR);lags=[]
  for j in range(s,e):
    if not(TE._drums(A,j) and TE._drums(B,j)):continue
    seg=lambda d,y:librosa.resample(y[int((j-d['start_bar'])*E.BAR*E.SR):][:L],orig_sr=E.SR,target_sr=22050)
    a,b=seg(A,ya),seg(B,yb)
    if min(len(a),len(b))<L*0.45:continue
    on=lambda y:librosa.onset.onset_strength(y=y,sr=22050,hop_length=64);lags.append(P.xlag_ms(on(a),on(b))[0])
  return float(np.median(lags)) if lags else None
@functools.lru_cache()
def gate():
  R=report();BO=TE.scores();PL={p['id']:p for p in P.meta().get('plan',[])};rows=[]
  for m in R['blends']:
    if not m['verdict'].startswith('FAIL'):continue
    k=m['k'];lag=direct_lag(k);bo=BO[k]['beatoff_bars'] if k<len(BO) and BO[k]['a']==m['a'] else None
    off=(lag is not None and abs(lag)>LAG_MS) or (bo is not None and bo>TE.BEATOFF_MAX_BARS)
    rows.append(dict(k=k,t=round(m['t0']/60,2),a=m['a'],b=m['b'],out_win=PL.get(m['a'],{}).get('out_win'),ears=m['verdict'],
      lag_ms=None if lag is None else round(lag,1),beatoff_bars=bo,status='confirmed' if off else 'suspect'))
  json.dump(rows,open(f'{C.SRC}/{C.NAME}_ears_gate.json','w'),indent=1);return rows
def test_ears_and_direct_drums_agree_no_blend_is_off():
  """Fail a blend only when ears flags it AND the direct drum check (deck onset lag > 20 ms or > 8 beat-off bars) agrees."""
  G=gate()
  for r in G:
    if r['status']=='suspect':warnings.warn(f"ears suspect {r['t']} min {r['a']}->{r['b']}: {r['ears']}, lag {r['lag_ms']} ms, beat-off {r['beatoff_bars']} bars")
  bad=[r for r in G if r['status']=='confirmed'];assert not bad,bad
