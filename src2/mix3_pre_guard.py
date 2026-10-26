import numpy as np,soundfile as sf,json,sys
from engine import *
from runs import runs_of
plan=json.load(open(sys.argv[sys.argv.index('--plan')+1] if '--plan' in sys.argv else 'plan.json'))
FX={k:sf.read(f'fx/{k}.wav',dtype='float32',always_2d=True)[0] for k in ['riser8','riser4','impact','roll8']}
decks=[];fxev=[];trans=[]
def info(b):
  r,nb=runs_of(b);tr=track(b);return r,nb,tr
def vact(b,k):
  v=track(b)['vact'];return bool(v[k]) if 0<=k<len(v) else False
def clean_drum_section(b,L=8):
  """phrase-aligned L-bar window with strong drums and least vocal (demucs stems)."""
  g=track(b)['g']['bar'];d=np.array(g.get('drums',g['all']));v=np.array(g.get('voc',[-100]*len(d)))
  cands=range(0,len(d)-L+1,L)
  return max(cands,key=lambda k:d[k:k+L].mean()-0.5*max(0,v[k:k+L].mean()+40))
def loop_extend(b,n,L=8,src0=None):
  """Reusable runway extender: loop a clean, vocal-free drums-stem section for n bars, phrase-aligned (wraps every L bars)."""
  if src0 is None: src0=clean_drum_section(b,L)
  return [(src0+(i%L),'drums') for i in range(n)],src0
def drumloop(src0,n,b=None): return loop_extend(b,n)[0] if b else [(src0+(i%8),'drums') for i in range(n)]
def first(b,pre):
  r,nb,_=info(b);dr=r[0][0];fb=max(0,dr-pre)
  d=Deck(b,0,fb,nb-fb,'open');d.drop=dr;decks.append(d);return d
def ramp(d,k,a,va,b_,vb):d.set(k,a,va);d.set(k,b_,vb)
def localbar(d,mixbar):return d.map[int(mixbar-d.start)][0] if 0<=mixbar-d.start<len(d.map) else None
def extend_out(A,upto,label):
  # ensure A has audio until mixbar 'upto'; loop drums stem of last full 8-bar drum section
  need=int(upto-A.end())
  if need>0:
    lp,src0=loop_extend(A.b,need);A.map+=lp;return f'{label}: outro loop-extended {need} bars (drums stem of bars {src0}-{src0+8})'
  A.map=A.map[:int(upto-A.start)];return None
def blend(A,b,pre=32,fade=16,hpf=False,acap=None,min_overlap=16,tail_drums=False,loop_intro=False,build=False,which=-1):
  r,nb,_=info(b);rA,nbA,_=info(A.b);dr=r[0][0]
  ae=rA[which][1]  # A bass end (local)
  # A's last bass end in mix bars: find index in map
  idx=[i for i,(s,st) in enumerate(A.map) if s==ae-1 and st=='mix'];swap=A.start+(idx[0]+1 if idx else len(A.map))
  notes=[]
  if loop_intro:
    B=Deck(b,swap-pre,0,0);B.map=loop_extend(b,pre)[0]+[(i,'mix') for i in range(dr,nb)];notes.append(f'intro replaced by {pre}-bar clean drums-stem loop (source intro grid unstable)')
  elif dr>=pre: B=Deck(b,swap-pre,dr-pre,nb-(dr-pre))
  else:
    B=Deck(b,swap-pre,0,0);B.map=loop_extend(b,pre-dr)[0]+[(i,'mix') for i in range(nb)];notes.append(f'intro loop-extended {pre-dr} bars (drums stem)')
  n=extend_out(A,swap+fade,'');notes+= [n] if n else []
  if tail_drums:
    for i in range(int((B.start if tail_drums=='early' else swap)-A.start),len(A.map)): A.map[i]=(A.map[i][0],'drums')
    notes.append('outgoing switched to its demucs drums stem '+('as the incoming intro enters (drum bridge)' if tail_drums=='early' else 'after the swap')+' (no harmonic overlap across the key change)')
  s=B.start
  ramp(B,'low',swap-0.25,0,swap,1);B.set('low',s,0)
  B.set('mid',s,0);B.set('mid',s+pre*0.5,0.6);B.set('mid',swap,1)
  B.set('high',s,0);B.set('high',s+8,1)
  ramp(A,'low',swap-0.25,1,swap,0)
  A.set('mid',swap,1);A.set('mid',swap+fade*0.6,0.5);A.set('mid',swap+fade,0)
  A.set('high',swap+fade*0.5,1);A.set('high',swap+fade,0)
  if hpf:A.set('hpf',swap,25);A.set('hpf',swap+fade,1800);notes.append('HP filter sweep on the outgoing track')
  # vocal clash control per bar (v3: explicit hold-at-1 around each muted bar; v2 let np.interp clamp the
  # outgoing deck's vocal to 0 / ramp it down for its whole run before the window)
  muted=0;mA=set();mB=set()
  for m in range(int(s),int(swap+fade)):
    a=A.map[m-A.start] if 0<=m-A.start<len(A.map) else None;bb=B.map[m-B.start]
    if a and a[1]=='mix' and bb[1]=='mix' and vact(A.b,a[0]) and vact(b,bb[0]):
      (mB if m<swap else mA).add(m);muted+=1
  def apply(D,ms):
    for m in sorted(ms):
      D.set('voc',m-0.06,0 if m-1 in ms else 1);D.set('voc',m-0.05,0);D.set('voc',m+0.95,0);D.set('voc',m+0.96,0 if m+1 in ms else 1)
  apply(A,mA);apply(B,mB)
  if build:
    B.set('hpf',swap-8,25);B.set('hpf',swap-0.05,900);B.set('hpf',swap,0)
    fxev.append(('riser8',swap,0.3));fxev.append(('roll8',swap,0.35 if build=='roll' else 0));fxev.append(('impact',swap,0.4))
    notes.append('8-bar tension build into the drop: HP-filter sweep up on the incoming, riser'+(' + snare roll' if build=='roll' else '')+' landing on the bass swap, impact on the one')
  decks.append(B);B.drop=dr
  if muted:notes.append(f'{muted} bars of vocal overlap avoided via demucs stem muting')
  if acap:
    # carry A's strongest 8-bar vocal phrase over B's post-drop? -> over B intro before swap
    v=np.array(track(A.b)['g']['bar']['voc']);best=max(range(0,len(v)-8,8),key=lambda k:v[k:k+8].mean())
    C=Deck(A.b,swap+acap,best,8);C.map=[(best+i,'vocals') for i in range(8)]
    C.set('gain',C.start,0);C.set('gain',C.start+1,0.85);C.set('gain',C.start+7,0.85);C.set('gain',C.start+8,0)
    C.set('low',C.start,0);decks.append(C);B.set('voc',C.start,0);B.set('voc',C.end(),0);B.set('voc',C.end()+0.25,1)
    notes.append(f'acapella layer: 8 bars of {A.b} vocal (src bars {best}-{best+8}) over {b}')
  trans.append(dict(tech=f'{pre}-bar beat-through blend + 3-band bass swap',a=A.b,b=b,start_bar=s,swap_bar=swap,end_bar=swap+fade,notes=notes))
  return B
def double(A,b,pre=16,hold=16,out=8,which=-1,at=0,slam=False):
  r,nb,_=info(b);rA,_,_=info(A.b);dr=r[0][0];ad=rA[which][0]+at
  idx=[i for i,(s,st) in enumerate(A.map) if s==ad and st=='mix'];drop=A.start+idx[0]
  B=Deck(b,drop-pre,dr-pre,nb-(dr-pre));s=B.start
  B.set('low',s,0);ramp(B,'low',drop-0.25,0,drop,1)
  B.set('mid',s,0);B.set('mid',drop-1,0.7);B.set('mid',drop,1);B.set('high',s,0);B.set('high',s+8,1)
  B.set('voc',s,0);ramp(B,'voc',drop-0.1,0,drop,1)
  if slam:
    B.auto={k:[] for k in B.auto};B.set('gain',s,0);B.set('gain',drop-0.02,0);B.set('gain',drop,1)
  ramp(A,'low',drop-0.25,1,drop,0);ramp(A,'voc',drop-0.25,1,drop,0)
  A.set('mid',drop,0.6);A.set('mid',drop+hold,0.6);A.set('mid',drop+hold+out,0)
  A.set('high',drop+hold,1);A.set('high',drop+hold+out,0)
  A.map=A.map[:int(drop+hold+out-A.start)]
  fxev.append(('riser8',drop,0.35));fxev.append(('impact',drop,0.5))
  decks.append(B);B.drop=dr
  trans.append(dict(tech='double drop (drops layered; incoming takes the bass, outgoing drums/top ride 16 bars)',a=A.b,b=b,start_bar=s,swap_bar=drop,end_bar=drop+hold+out,notes=['self-made riser into the drop + impact']+(['slam: incoming held silent until the drop, riser over the outgoing carries the build'] if slam else [])))
  return B
def echo(A,b,pre=32,which=-1,roll=True,lead=0,ride=False,outro=0):
  r,nb,_=info(b);rA,_,_=info(A.b);dr=r[0][0];ae=rA[which][1]
  idx=[i for i,(s,st) in enumerate(A.map) if s==ae-1 and st=='mix'];E=A.start+min(idx[0]+1+outro,len(A.map))  # outro: let A play its own outro (in-source energy step-down) before the echo cut
  A.map=A.map[:int(E-A.start)];A.echo=True
  B=Deck(b,E,max(0,dr-pre),nb-max(0,dr-pre));B.set('high',E,0.3);B.set('high',E+4,1)
  if lead:
    f0=max(0,dr-pre);lm=[(f0-lead+i,'drums') for i in range(lead)] if f0>=lead else loop_extend(b,lead)[0]
    B.start=E-lead;B.map=lm+B.map;B.set('gain',E-lead,0.0);B.set('gain',E-lead+4,0.8);B.set('gain',E,1)
  decks.append(B);B.drop=dr;fxev.append(('impact',E,0.35))
  D=E+min(pre,dr)
  B.set('hpf',D-8,25);B.set('hpf',D-0.05,1100);B.set('hpf',D,0)
  if ride:  # incoming's own drop drums (stem) loop under its intro from the cut to the drop: drum-led build, no harmonic overlap
    R=Deck(b,E,dr,int(D-E));R.map=[(dr+(i%8),'drums') for i in range(int(D-E))];R.set('gain',E,0.75);R.set('gain',D-0.05,0.9)
    R.set('hpf',D-8,25);R.set('hpf',D-0.05,1100);R.set('hpf',D,0);R.drop=-1;R.label='drum ride';decks.append(R)
  fxev.append(('riser8',D,0.3))
  if roll: fxev.append(('roll8',D,0.35))
  fxev.append(('impact',D,0.45))
  st0=B.start
  trans.append(dict(tech=(f'echo-out wash (1/2-beat ping-pong tail) into a {min(pre,dr)}-bar breakdown, 8-bar filter+riser' if pre else 'echo-out wash with an 8-bar riser over the outgoing tail, slamming straight into the incoming drop')+(' +snare-roll' if roll else '')+' build into the drop',a=A.b,b=b,start_bar=st0,swap_bar=E,end_bar=E+4,notes=['key change handled with zero harmonic overlap','tension builds into the drop (fix for 02b Around Me)']+([f'incoming drums stem rides {lead} bars under the outgoing before the echo cut (keeps energy up, no harmonic overlap)'] if lead else [])+(['incoming drop-drums stem loops under its intro from the cut to the drop (drum-led build)'] if ride else [])))
  return B
# ---- execute plan
cur=None
for step in plan:
  t=step['tech'];b=step['id'];kw=step.get('kw',{})
  if t=='first':cur=first(b,**kw)
  elif t=='blend':cur=blend(cur,b,**kw)
  elif t=='double':cur=double(cur,b,**kw)
  elif t=='echo':cur=echo(cur,b,**kw)
total=max(d.end() for d in decks)+12
if '--dry' in sys.argv:
  print('len min',round(total*BAR/60,2))
  for t in trans:print(round(t['start_bar']*BAR/60,2),t['a'],'->',t['b'],t['tech'],t['notes'])
  for d in decks:print(d.b,d.start,d.end(),round(d.start*BAR/60,2))
  sys.exit()
N=int(total*BS);M=np.zeros((N,2),np.float32)
import engine,gc
for j,d in enumerate(decks):
  y=d.render().astype(np.float32);i0=int(round(d.start*BS));M[i0:i0+len(y)]+=y[:N-i0]
  if d.echo:
    lastbeat=y[-int(BEAT*SR):];tail=echo_tail(lastbeat);i1=i0+len(y);M[i1:i1+len(tail)]+=tail[:N-i1]*0.9
  need={x.b for x in decks[j+1:]}
  for k in list(engine._cache):
    if k not in need: engine._cache[k]['st']={}
  d.tr=None;del y;gc.collect()
for k,bar,gn in fxev:
  x=FX[k];i0=int(round(bar*BS))-(len(x) if k.startswith('riser') else 0);M[i0:i0+len(x)]+=x*gn
end=int(total*BS);e=np.abs(M).mean(1);last=len(e)-np.argmax(e[::-1]>1e-4);M=M[:last+SR]
OUT=sys.argv[sys.argv.index('--out')+1] if '--out' in sys.argv else 'mix2';PLAN=None
sf.write(OUT+'_raw.wav',M,SR,subtype='FLOAT')
meta=dict(decks=[dict(full_map=d.map,echo=bool(d.echo),auto={k:sorted(v) for k,v in d.auto.items()},id=d.b,start_bar=d.start,end_bar=d.end(),map=d.map[:1]+d.map[-1:],label=d.label,drop_bar=(d.start+[i for i,(s,_) in enumerate(d.map) if s==getattr(d,'drop',-1)][0]) if any(s==getattr(d,'drop',-1) for s,_ in d.map) else None, acap=d.map[0][1]=='vocals') for d in decks],trans=trans,plan=plan,bar_sec=BAR,len_sec=len(M)/SR)
json.dump(meta,open(OUT+'_meta.json','w'),indent=1,default=float)
print('len min',round(len(M)/SR/60,2))
for t in trans:print(round(t['start_bar']*BAR/60,2),t['a'],'->',t['b'],t['tech'],t['notes'])
