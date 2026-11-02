"""See-saw / pumping detector for blends (the listener 2026-10-31, Mix 06 27:35 Remedy>Ignite: 'two tracks fighting, fading randomly in and out').
Per-bar level of each deck = source per-beat level at the mapped source bar + 20log10(deck gain); mix level = power sum.
Fails a blend when
  OUT_RISE : the outgoing deck jumps UP by > OUT_RISE_DB bar-to-bar while it is fading (a looped phrase whose last bars are quieter restarts loud)
  WOBBLE   : the summed level reverses direction with swings >= WOB_DB at least WOB_N times inside the blend
  ANTI     : the two decks' bar-to-bar changes are anti-correlated (r <= ANTI_R) while both move >= ANTI_DB rms (see-saw)"""
import json,os,numpy as np
import plan_search as P
OUT_RISE_DB=float(os.environ.get('SEESAW_OUT_RISE',4.5));WOB_DB=float(os.environ.get('SEESAW_WOB_DB',2.5));WOB_N=int(os.environ.get('SEESAW_WOB_N',4))
TRADE_DB=float(os.environ.get('SEESAW_TRADE_DB',3.0));TRADE_N=int(os.environ.get('SEESAW_TRADE_N',2))
ANTI_R=float(os.environ.get('SEESAW_ANTI_R',-0.5));ANTI_DB=float(os.environ.get('SEESAW_ANTI_DB',2.0))
_B={}
def _beats(i):
  if i not in _B:
    cw=os.getcwd();os.chdir(os.path.dirname(os.path.abspath(__file__)))
    try:_B[i]=P.PF.beats(i)[0]
    finally:os.chdir(cw)
  return _B[i]
_D={}
def _dnb(i):
  if i not in _D:
    cw=os.getcwd();os.chdir(os.path.dirname(os.path.abspath(__file__)))
    try:import beatstem;_D[i]=beatstem.levels(i)
    finally:os.chdir(cw)
  return _D[i]
def deck_bars(d,b0,b1):
  bt=_beats(d['id']);g=np.array(d['auto']['gain']);out=[]
  for mb in range(b0,b1):
    j=int(mb-d['start_bar'])
    if j<0 or j>=len(d['full_map']):out.append(-120.0);continue
    sb,srcn=d['full_map'][j][0],d['full_map'][j][1];lv=(_dnb(d['id']) if srcn=='beat' else bt)[sb*4:sb*4+4];lv=10*np.log10(np.mean(10**(np.array(lv)/10))) if len(lv) else -120  # beat-only synthetic outro bars: drums+bass stem level
    gg=np.mean([np.interp(mb+q/4,g[:,0],g[:,1]) for q in range(4)]);out.append(lv+20*np.log10(max(gg,1e-6)))
  return np.array(out)
def reversals(x,th):
  n=0;last=0;ref=x[0]
  for v in x[1:]:
    d=v-ref
    if abs(d)>=th:
      s=np.sign(d)
      if last and s!=last:n+=1
      last=s;ref=v
    elif (last>0 and v>ref) or (last<0 and v<ref):ref=v
  return n
def blend(M,i):
  t=M['trans'][i];D={d['id']:d for d in M['decks']};A,B=D[t['a']],D[t['b']];b0,b1=int(t['start_bar']),int(t['end_bar'])
  a,b=deck_bars(A,b0,b1),deck_bars(B,b0,b1);s=10*np.log10(10**(a/10)+10**(b/10))
  rise=float(np.max(np.diff(a))) if len(a)>1 else 0;wob=reversals(s,WOB_DB)
  da,db=np.diff(a),np.diff(b);ok=(a[1:]>-60)&(b[1:]>-60)
  r=float(np.corrcoef(da[ok],db[ok])[0,1]) if ok.sum()>4 and da[ok].std()>0 and db[ok].std()>0 else 0.0
  anti=r<=ANTI_R and da[ok].std()>=ANTI_DB and db[ok].std()>=ANTI_DB
  fl=flips(a,b,TRADE_DB)
  # 2026-11-01 19:20 ET the listener calibration (eval/calibration_notes.md): the see-saw that blocks is decks TRADING the lead
  # (louder deck flips back and forth, Remedy>Ignite 28:00 rated 2: 3 flips) or anti-correlated swings. An outgoing rise in its own
  # arrangement (OUT_RISE) or summed wobble alone is a warning: he rated 2B/3B good with those.
  fails=[k for k,v in dict(TRADE=fl>=TRADE_N,ANTI=anti).items() if v]
  warns=[k for k,v in dict(OUT_RISE=rise>OUT_RISE_DB,WOBBLE=wob>=WOB_N).items() if v]
  return dict(i=i,a=t['a'],b=t['b'],t=t['start_bar']*M['bar_sec'],out_rise=round(rise,1),wobble=wob,anti_r=round(r,2),lead_flips=fl,fails=fails,warns=warns)
def flips(a,b,h):
  """times the louder deck changes (by >= h dB, hysteresis) while either is audible; a clean blend flips once (out -> in)"""
  st=n=0
  for x,y in zip(a,b):
    if x<-50 and y<-50:continue
    d=x-y;s=1 if d>=h else -1 if d<=-h else 0
    if s and st and s!=st:n+=1
    if s:st=s
  return n
def check(M):return [blend(M,i) for i in range(len(M['trans']))]
if __name__=='__main__':
  import sys
  for r in check(json.load(open(sys.argv[1]))):print(f"{int(r['t']//60)}:{int(r['t']%60):02d} {r['a'][:4]}>{r['b'][:4]} rise {r['out_rise']} wob {r['wobble']} r {r['anti_r']} {r['fails']}")
