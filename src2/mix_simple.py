"""The mix engine (crossfader only, the listener 2026-10-28): two decks, ONE crossfader x(t) 0->1 per blend,
deck gains derived only from x (equal-power), channel faders at unity, no stems/EQ/ducking in playback.
Vocal clashes avoided by choosing mix points from full-track analysis; else loop a clean instrumental
phrase (seams overlap-added at bar boundaries).
Blend length: XBARS (default 32) per blend, falling back to 16 (the minimum) only when no clean 32-bar window exists.
Bass handoff (BASS_SWAP_BARS, default 2; 0 = off): the only EQ move, tied to the crossfader. When x passes SWAP_POS
(default 0.35, Raveform median ~0.36) the outgoing deck's low band (<150 Hz) ramps 1->0 while the incoming one ramps
0->1 (raised cosine, monotonic), so one bassline plays at a time.
Window choice uses cached Demucs activity maps (bar.voc, bar.bass) for analysis only."""
import numpy as np,soundfile as sf,json,sys,os
from engine import track,render_deck,SR,BAR,BEAT,BS
plan=json.load(open(sys.argv[sys.argv.index('--plan')+1]));OUT=sys.argv[sys.argv.index('--out')+1]
X=int(sys.argv[sys.argv.index('--xbars')+1]) if '--xbars' in sys.argv else int(os.environ.get('XBARS',32))
POS=float(os.environ.get('SWAP_POS',0.35))  # bass handoff centre as a fraction of the blend (Raveform median ~0.36)
ids=[p['id'] for p in plan]
def A_(b):
  t=track(b);al=np.array(t['g']['bar']['all'],float);return t,al,np.percentile(al,75),np.array(t['vact'],bool),t['nb']
def tail0(al,body):
  loud=np.where(al>body-20)[0];return int(loud[-1])+1 if len(loud) else len(al)
def clean_phrases(b):
  t,al,body,v,nb=A_(b);return [p for p in range(0,nb-15,16) if v[p:p+16].sum()<=1 and al[p:p+16].mean()>body-6]
# per-track in/out plan: score every phrase-aligned candidate window by simulating the guardrails
# (V1 vocal clash, L1 double bass, O1 both audible >=8 bars, C2 outgoing not too quiet) under the crossfader.
ANCH={p['id'] for p in plan if p.get('anchor')};NOIN={p['id'] for p in plan if p.get('anchor_in') is False};HEAVY=float(os.environ.get('HEAVY',-6))
SW=float(os.environ.get('BASS_SWAP_BARS',2))
def F(b):
  g=track(b)['g']['bar'];al=np.array(g['all'],float);lo=np.array(g['low'],float);v=np.array(g.get('voc',[-100]*len(al)),float)
  bs=np.array(g['bass'],float) if 'bass' in g else None
  bact=(bs>np.percentile(bs,90)-10) if bs is not None else (lo-al>HEAVY)
  hi=10*np.log10(np.maximum(10**(al/10)-10**(lo/10),1e-10))  # level above the bass band (what stays audible through the handoff)
  return hi,lo,v,float(np.percentile(v,95)),bact
_ON={}
def onsets(b):  # per-bar onset envelope (cached), used only to predict guardrail R1 (drums fighting)
  if b in _ON:return _ON[b]
  f=f'st/{b}.onset.npy'
  if os.path.exists(f):_ON[b]=np.load(f);return _ON[b]
  import librosa;tr=track(b);x=tr['st']['mix'];x=x.mean(1) if x.ndim>1 else x;L=int(BAR*SR);out=[]
  for k in range(tr['nb']):
    j=int(round((tr['d0']+k*BAR)*SR));seg=np.asarray(x[max(0,j):j+L],np.float32)
    if len(seg)<L:seg=np.pad(seg,(0,L-len(seg)))
    out.append(librosa.onset.onset_strength(y=seg,sr=SR,hop_length=512))
  n=min(len(o) for o in out);_ON[b]=np.array([o[:n] for o in out]);np.save(f,_ON[b]);return _ON[b]
def rxc(a,b,wa,wb):
  oa,ob=onsets(a),onsets(b);ml=max(1,int((BEAT/8)*(SR/512)));xs=[]
  for xa,xb in zip(wa,wb):
    if xa>=len(oa) or xb>=len(ob):continue
    ea=oa[xa]-oa[xa].mean();eb=ob[xb]-ob[xb].mean();na,nb_=np.linalg.norm(ea),np.linalg.norm(eb)
    if na<1e-9 or nb_<1e-9:continue
    c=np.correlate(ea/na,eb/nb_,mode='full');m=len(c)//2;xs.append(float(c[m-ml:m+ml+1].max()))
  return float(np.median(xs)) if xs else 1.0
def score(a,b,wa,wb,refA):
  alA,loA,vA,rvA,bA=F(a);alB,loB,vB,rvB,bB=F(b);V=L=C=both=G=SG=0
  for k,(xa,xb) in enumerate(zip(wa,wb)):
    x=(k+0.5)/X;ga,gb=np.cos(x*np.pi/2),np.sin(x*np.pi/2);da,dbb=20*np.log10(ga),20*np.log10(gb)
    LA,LB=alA[xa]+da,alB[xb]+dbb
    if LA>refA-12 and LB>refA-12:both+=1
    if k<X/2 and LA<refA-10:C+=1
    if vA[xa]>rvA-12 and ga>0.3 and vB[xb]>rvB-12 and gb>0.3:V+=1
    if SW>0:  # with the bass handoff only the swap bars can double up; elsewhere the bassline must not drop out
      if abs(k+0.5-POS*X)<SW/2+0.5:
        if bA[xa] and bB[xb]:L+=1
      elif (k<POS*X and not bA[xa]) or (k>=POS*X and not bB[xb]):
        G+=1;SG+=int(POS*X<=k<POS*X+4)  # incoming has no bass right after the handoff: audible energy drop
    elif loA[xa]-alA[xa]>HEAVY and loB[xb]-alB[xb]>HEAVY and min(loA[xa]+da,loB[xb]+dbb)>refA-12:L+=1
  return dict(V=V,L=L,C=C,both=both,G=G,SG=SG,pen=float(os.environ.get('SGPEN',15))*SG+float(os.environ.get('VPEN',100))*V+4*L+float(os.environ.get('BOTHPEN',15))*max(0,10-both)+3*C+float(os.environ.get('GAPPEN',0.5))*G)
XT={};inn={ids[0]:0};outs={};loops={};notes={};info_={}
def pair_cands(i,ia0):
  """all scored windows for blend i given where track i starts (ia0); sorted best first"""
  global X
  a,b=ids[i],ids[i+1];ta,ala,ba,va,na=A_(a);tb,alb,bb,vb,nb=A_(b)
  ia=ia0[1]+16 if isinstance(ia0,tuple) else ia0;res=[]
  e_max=min(tail0(ala,ba),na);e_max-=e_max%16
  minlen=160 if a in ANCH else 96-X  # anchors: >=160 bars (~220 s) of their own music, blend included
  emin=max(ia+minlen,ia+int((e_max-ia)*0.5));emin+=(-emin)%16;emin=min(emin,e_max)
  XMAX=X
  for X in sorted({XMAX,16},reverse=True):  # 32-bar blend preferred; 16 is the minimum when no clean 32-bar window exists
    cands=[]
    for e in range(e_max,emin-1,-16):
      for ib in range(0,min(81,nb-3*X),16):cands.append(('n',e,ib))
    eml=max(ia+16,emin-X) if a in ANCH else emin  # anchors: looped bars count toward their >=160 bars of airtime
    for e in range(e_max,eml-1,-16):  # outgoing plays to e, then repeats its own clean 16-bar phrase p under the blend
      for p in range(max(ia,16),e-15,16):
        for ib in range(0,min(81,nb-3*X),16):cands.append(('la',(e,p),ib))
    for e in range(e_max,emin-1,-16):
      for q in range(16,min(97,nb-4*X),16):cands.append(('lb',e,q))  # incoming plays phrase q first, continues q+16
    cpa=[p for p in clean_phrases(a) if p>=max(ia,16)];cpb=[q for q in clean_phrases(b) if 16<=q<min(97,nb-4*X)]
    for e in range(e_max,emin-1,-16):  # both decks loop a clean instrumental phrase (only when neither has vocal-free runway)
      for p in [p for p in cpa if p<=e-16]:
        for q in cpb:cands.append(('ab',(e,p),q))
    if b in ANCH and b not in NOIN:  # incoming anchor: start early enough to keep >=160 bars of its own music
      bmx=min(tail0(alb,bb),nb)-160;cands=[c for c in cands if c[2]<=max(0,bmx)] or cands
    LW=float(os.environ.get('LW',0.4))
    for kind,e,ib in cands:
      if kind in('la','ab'):e,p=e;wa=[p+(k%16) for k in range(X)];ea=e
      else:wa=range(e-X,e);ea=e
      q=ib;wb=[q+(k%16) for k in range(X)] if kind in('lb','ab') else range(q,q+X)
      ha=F(a)[0];ref=float(np.median(ha[max(ia,ea-X-8):ea-X])) if kind not in('la','ab') else float(np.median(ha[e-8:e]))
      r=score(a,b,list(wa),list(wb),ref)
      step=(max(abs(np.median(ala[e-4:e])-np.median(ala[p:p+4])),abs(np.mean(ala[e-2:e])-np.mean(ala[p:p+2]))) if kind in('la','ab') else 0)+(abs(alb[q]-alb[q+15]) if kind in('lb','ab') else 0)  # level jump at the loop seam
      r['pen']+=float(os.environ.get('SEAMPEN',8))*max(0,step-2);r['R']=round(rxc(a,b,list(wa),list(wb)),3);r['pen']+=float(os.environ.get('RPEN',300))*max(0,0.25-r['R'])
      skipped=(e_max-ea)+ib  # bars of music not heard
      seq=[(e-1 if kind in('la','ab') else wa[0]-1)]+list(wa)[:X//2+2];seq=[k for k in seq if 0<=k<len(ha)]
      jump=max([abs(ha[seq[k]]-ha[seq[k-1]]) for k in range(1,len(seq))]+[0])  # outgoing level jumps across entry / first half (guardrail N1, C1)
      r['pen']+=float(os.environ.get('SEAMPEN',8))*max(0,jump-3)
      hole=int(any(alb[k]<float(os.environ.get('HOLE_DB',-31)) for k in range(q+X,min(q+X+96,tail0(alb,bb)))))  # incoming would play a near-silent bar of its own (guardrail E2)
      r['pen']+=float(os.environ.get('HOLEPEN',0))*hole
      if step>float(os.environ.get('SEAMMAX',2)) or r['both']<int(os.environ.get('BOTHMIN',11)):r['pen']+=float(os.environ.get('HARDPEN',60))  # hard limits: guardrail N1 (3 dB step) and O1 (>=8 bars)
      sc=(r['pen']+(float(os.environ.get('SHORTPEN',6)) if X<XMAX else 0)+LW*skipped+float(os.environ.get('LOOPPEN',6))*{'n':0,'la':1,'lb':1,'ab':2}[kind],-ea,str(ib))
      res.append((sc,kind,(e,p) if kind in('la','ab') else e,ib,r,X))
  X=XMAX;res.sort(key=lambda t:t[0]);return res
def nxt_inn(c):return ("loopB",c[3]) if c[1] in("lb","ab") else c[3]
LOOK=int(os.environ.get("LOOKAHEAD",8))
for i in range(len(ids)-1):
  a,b=ids[i],ids[i+1];cs=pair_cands(i,inn[a])
  if i+1<len(ids)-1 and LOOK>1:best=min(cs[:LOOK],key=lambda c:c[0][0]+pair_cands(i+1,nxt_inn(c))[0][0][0])  # 1-step lookahead: do not starve the next blend
  else:best=cs[0]
  _,kind,e,ib,r,xt=best;XT[(a,b)]=xt;n=[]
  if kind=='ab':e,p=e;loops[a]=p;n.append(f'outgoing plays to bar {e}, then repeats its clean phrase {p}-{p+16}; incoming loops its clean phrase {ib}-{ib+16} through the blend, then continues from bar {ib+16}');ib=('loopB',ib)
  elif kind=='la':e,p=e;loops[a]=p;n.append(f'outgoing plays to bar {e}, then repeats its 16-bar phrase {p}-{p+16} under the blend (cleaner window than its real outro)')
  elif kind=='lb':n.append(f'incoming plays its 16-bar phrase {ib}-{ib+16} through the blend, then continues from bar {ib+16}');ib=('loopB',ib)
  else:n.append(f'mix points from full-track analysis: outgoing out at bar {e}, incoming in at bar {ib}')
  outs[a]=e;inn[b]=ib;notes[(a,b)]=(n,r['V']);info_[(a,b)]=r
  print('choose',a,b,kind,xt,r,file=sys.stderr)
outs[ids[-1]]=tail0(*A_(ids[-1])[1:3])
# build deck maps (src bar list) ; deck plays inn..out, outgoing loop appended for X bars
decks=[];start=0
for i,b in enumerate(ids):
  ib=inn[b]
  xi=XT.get((ids[i-1],b),X) if i else X;xo=XT.get((b,ids[i+1]),X) if i<len(ids)-1 else 0
  if isinstance(ib,tuple):m=[ib[1]+(k%16) for k in range(xi)];first=ib[1]+16;m+=list(range(first,outs[b]))
  else:m=list(range(ib,outs[b]))
  if b in loops and i<len(ids)-1:m=m+[loops[b]+(k%16) for k in range(xo)]
  decks.append(dict(id=b,start_bar=start,full_map=[[s,'mix'] for s in m]));start=start+len(m)-xo
import os;sys.path.insert(0,'../src/tests');os.environ.setdefault('MIX_SRC','.');import checks as _C;KEYS=_C.keys()
trans=[]
for i in range(len(ids)-1):
  A,B=decks[i],decks[i+1];X=XT[(A['id'],B['id'])];s=B['start_bar'];e=s+X
  xs=[[s+k/4,round(k/(4*X),5)] for k in range(4*X+1)]  # crossfader position per beat, linear 0->1
  n,cl=notes[(A['id'],B['id'])]
  trans.append(dict(tech=f'{X}-bar crossfader blend (equal-power, single control)'+(f' + {SW:g}-bar bass handoff' if SW>0 else ''),a=A['id'],b=B['id'],start_bar=s,swap_bar=s+int(round(POS*X)),end_bar=e,xfader=xs,vocal_clash_bars=cl,keys=f"{KEYS.get(A['id'])}->{KEYS.get(B['id'])}",key_ok=bool(_C.camelot_ok(KEYS.get(A['id']),KEYS.get(B['id']))),pitch_shift_semitones=0,bass_swap=[s+round(POS*X)-SW/2,s+round(POS*X)+SW/2] if SW>0 else None,notes=n or ['vocal-free mix points chosen from full-track analysis']))
def gA(x):return float(np.cos(x*np.pi/2))
def gB(x):return float(np.sin(x*np.pi/2))
for i,d in enumerate(decks):
  g=[]
  if i>0:g+=[[p[0],gB(p[1])] for p in trans[i-1]['xfader']]
  if i<len(decks)-1:g+=[[p[0],gA(p[1])] for p in trans[i]['xfader']]
  d['auto']={'gain':g}
  if SW>0:
    lo=[]
    def ramp(c,up):
      return [[c-SW/2+SW*j/16,round(float((1-np.cos(np.pi*j/16))/2 if up else (1+np.cos(np.pi*j/16))/2),5)] for j in range(17)]
    if i>0:lo+=ramp(trans[i-1]['swap_bar'],True)
    if i<len(decks)-1:lo+=ramp(trans[i]['swap_bar'],False)
    d['auto']['low']=lo
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
