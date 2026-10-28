"""The mix engine (crossfader only, the listener 2026-10-28): two decks, ONE crossfader x(t) 0->1 per blend,
deck gains derived only from x (equal-power), channel faders at unity, no stems/EQ/ducking in playback.
Vocal clashes avoided by choosing mix points from full-track analysis; else loop a clean instrumental
phrase (seams overlap-added at bar boundaries)."""
import numpy as np,soundfile as sf,json,sys,os
from engine import track,render_deck,SR,BAR,BEAT,BS
plan=json.load(open(sys.argv[sys.argv.index('--plan')+1]));OUT=sys.argv[sys.argv.index('--out')+1]
X=int(sys.argv[sys.argv.index('--xbars')+1]) if '--xbars' in sys.argv else 16
ids=[p['id'] for p in plan]
def A_(b):
  t=track(b);al=np.array(t['g']['bar']['all'],float);return t,al,np.percentile(al,75),np.array(t['vact'],bool),t['nb']
def tail0(al,body):
  loud=np.where(al>body-20)[0];return int(loud[-1])+1 if len(loud) else len(al)
def clean_phrases(b):
  t,al,body,v,nb=A_(b);return [p for p in range(0,nb-15,16) if v[p:p+16].sum()<=1 and al[p:p+16].mean()>body-6]
# per-track in/out plan: score every phrase-aligned candidate window by simulating the guardrails
# (V1 vocal clash, L1 double bass, O1 both audible >=8 bars, C2 outgoing not too quiet) under the crossfader.
ANCH={p['id'] for p in plan if p.get('anchor')};HEAVY=float(os.environ.get('HEAVY',-6))
def F(b):
  g=track(b)['g']['bar'];al=np.array(g['all'],float);lo=np.array(g['low'],float);v=np.array(g.get('voc',[-100]*len(al)),float)
  return al,lo,v,float(np.percentile(v,95))
def score(a,b,wa,wb,refA):
  alA,loA,vA,rvA=F(a);alB,loB,vB,rvB=F(b);V=L=C=both=0
  for k,(xa,xb) in enumerate(zip(wa,wb)):
    x=(k+0.5)/X;ga,gb=np.cos(x*np.pi/2),np.sin(x*np.pi/2);da,dbb=20*np.log10(ga),20*np.log10(gb)
    LA,LB=alA[xa]+da,alB[xb]+dbb
    if LA>refA-12 and LB>refA-12:both+=1
    if k<X/2 and LA<refA-10:C+=1
    if vA[xa]>rvA-12 and ga>0.3 and vB[xb]>rvB-12 and gb>0.3:V+=1
    if loA[xa]-alA[xa]>HEAVY and loB[xb]-alB[xb]>HEAVY and min(loA[xa]+da,loB[xb]+dbb)>refA-12:L+=1
  return dict(V=V,L=L,C=C,both=both,pen=10*V+4*L+6*max(0,8-both)+3*C)
inn={ids[0]:0};outs={};loops={};notes={};info_={}
for i in range(len(ids)-1):
  a,b=ids[i],ids[i+1];ta,ala,ba,va,na=A_(a);tb,alb,bb,vb,nb=A_(b)
  ia=inn[a];ia=ia[1]+16 if isinstance(ia,tuple) else ia;best=None
  e_max=min(tail0(ala,ba),na);e_max-=e_max%16
  minlen=160 if a in ANCH else 96
  emin=max(ia+minlen-X,ia+int((e_max-ia)*0.5));emin+=(-emin)%16
  cands=[]
  for e in range(e_max,emin-1,-16):
    for ib in range(0,min(49,nb-3*X),16):cands.append(('n',e,ib))
  for e in range(e_max,emin-1,-16):  # outgoing plays to e, then repeats its own clean 16-bar phrase p under the blend
    for p in range(max(ia,16),e-15,16):
      for ib in range(0,min(49,nb-3*X),16):cands.append(('la',(e,p),ib))
  for e in range(e_max,emin-1,-16):
    for q in range(16,min(65,nb-4*X),16):cands.append(('lb',e,q))  # incoming plays phrase q first, continues q+16
  LW=float(os.environ.get('LW',0.15))
  for kind,e,ib in cands:
    if kind=='la':e,p=e;wa=range(p,p+16);ea=e
    else:wa=range(e-X,e);ea=e
    q=ib;wb=range(q,q+X)
    ref=float(np.median(ala[max(ia,ea-X-8):ea-X])) if kind!='la' else float(np.median(ala[e-8:e]))
    r=score(a,b,list(wa),list(wb),ref)
    skipped=(e_max-ea)+(ib if kind!='lb' else ib)  # bars of music not heard
    sc=(r['pen']+LW*skipped+(float(os.environ.get('LOOPPEN',3)) if kind!='n' else 0),-ea,str(ib))
    if best is None or sc<best[0]:best=(sc,kind,(e,p) if kind=='la' else e,ib,r)
  _,kind,e,ib,r=best;n=[]
  if kind=='la':e,p=e;loops[a]=p;n.append(f'outgoing plays to bar {e}, then repeats its 16-bar phrase {p}-{p+16} under the blend (cleaner window than its real outro)')
  elif kind=='lb':n.append(f'incoming plays its 16-bar phrase {ib}-{ib+16} through the blend, then continues from bar {ib+16}');ib=('loopB',ib)
  else:n.append(f'mix points from full-track analysis: outgoing out at bar {e}, incoming in at bar {ib}')
  outs[a]=e;inn[b]=ib;notes[(a,b)]=(n,r['V']);info_[(a,b)]=r
  print('choose',a,b,kind,r,file=sys.stderr)
outs[ids[-1]]=tail0(*A_(ids[-1])[1:3])
# build deck maps (src bar list) ; deck plays inn..out, outgoing loop appended for X bars
decks=[];start=0
for i,b in enumerate(ids):
  ib=inn[b]
  if isinstance(ib,tuple):m=[ib[1]+(k%16) for k in range(X)];first=ib[1]+16;m+=list(range(first,outs[b]))
  else:m=list(range(ib,outs[b]))
  if b in loops and i<len(ids)-1:m=m+[loops[b]+(k%16) for k in range(X)]
  decks.append(dict(id=b,start_bar=start,full_map=[[s,'mix'] for s in m]));start=start+len(m)-X
import os;sys.path.insert(0,'../src/tests');os.environ.setdefault('MIX_SRC','.');import checks as _C;KEYS=_C.keys()
trans=[]
for i in range(len(ids)-1):
  A,B=decks[i],decks[i+1];s=B['start_bar'];e=s+X
  xs=[[s+k/4,round(k/(4*X),5)] for k in range(4*X+1)]  # crossfader position per beat, linear 0->1
  n,cl=notes[(A['id'],B['id'])]
  trans.append(dict(tech=f'{X}-bar crossfader blend (equal-power, single control)',a=A['id'],b=B['id'],start_bar=s,swap_bar=s+X//2,end_bar=e,xfader=xs,vocal_clash_bars=cl,keys=f"{KEYS.get(A['id'])}->{KEYS.get(B['id'])}",key_ok=bool(_C.camelot_ok(KEYS.get(A['id']),KEYS.get(B['id']))),pitch_shift_semitones=0,notes=n or ['vocal-free mix points chosen from full-track analysis']))
def gA(x):return float(np.cos(x*np.pi/2))
def gB(x):return float(np.sin(x*np.pi/2))
for i,d in enumerate(decks):
  g=[]
  if i>0:g+=[[p[0],gB(p[1])] for p in trans[i-1]['xfader']]
  if i<len(decks)-1:g+=[[p[0],gA(p[1])] for p in trans[i]['xfader']]
  d['auto']={'gain':g}
  d['end_bar']=d['start_bar']+len(d['full_map']);d['echo']=False;d['label']='';d['map']=d['full_map'][:1]+d['full_map'][-1:];d['acap']=False;d['drop_bar']=None
if '--dry' in sys.argv:
  for t in trans:print(round(t['start_bar']*BAR/60,2),t['a'],'->',t['b'],t['vocal_clash_bars'],t['notes'])
  print('len min',round((decks[-1]['end_bar'])*BAR/60,2));sys.exit()
total=decks[-1]['end_bar'];N=int(total*BS)+SR;M=np.zeros((N,2),np.float32)
import engine
for j,d in enumerate(decks):
  y=render_deck(d);i0=int(round(d['start_bar']*BS));M[i0:i0+len(y)]+=y[:N-i0]
  need={x['id'] for x in decks[j+1:]}
  for k in list(engine._cache):
    if k not in need:engine._cache[k]['st'].clear()
sf.write(OUT+'_raw.wav',M,SR,subtype='FLOAT')
json.dump(dict(engine='simple_crossfader',decks=decks,trans=trans,fx=[],plan=plan,bar_sec=BAR,len_sec=len(M)/SR),open(OUT+'_meta.json','w'),indent=1,default=float)
print('len min',round(len(M)/SR/60,2))
for t in trans:print(round(t['start_bar']*BAR/60,2),t['a'],'->',t['b'],t['vocal_clash_bars'],t['notes'])
