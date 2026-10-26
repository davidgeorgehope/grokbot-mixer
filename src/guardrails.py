#!/usr/bin/env python3
"""Deterministic, fail-hard audio guardrails for a rendered mix (mix3.py meta + raw wav + mastered mp3).
usage: guardrails.py --src DIR --name NAME --mp3 MP3 [--out DIR] [--png] [--only 13:00-15:00,36:00-40:00]
Exit 0 = zero failures. Writes OUT/guardrails.json (summary+failures with timestamps) and, with --png,
OUT/trans_XX_MMSS.png per transition (+ win_MMSS.png for flagged windows inside a track).
Checks (ids used in the report):
 E1 energy hole  : short-term (3 s) loudness > 6 dB under the local 30 s median, outside declared/intentional breakdowns
 E2 near silence : momentary (400 ms) loudness < -35 LUFS anywhere except the first/last 5 s
 N1 entry shock  : incoming deck's first beats off the master grid (>10 ms) or master level step at entry > 3 dB
 F1 flam         : per overlap bar, beat-phase offset between the two decks (each rendered alone) > 15 ms
 G1 grid         : master beat-phase jitter between adjacent 2-bar windows > 8 ms, or > 15 ms off the global grid
 K1 key clash    : Camelot distance > 2 during a harmonic overlap that is not an echo/cut transition
 L1 low end      : summed sub (<120 Hz) > +3 dB over the louder deck alone, or both decks' sub 'full' at once
 V1 vocal clash  : two decks audibly singing in the same bar (demucs vocal stems)
 P1 peak/DC      : true peak > -1 dBTP or |DC| > 0.005
 D1 dropped drop : a deck's drop (bass in) without a build in the 8 bars before (riser/HPF build/echo, or +3 dB ramp)
 X1 no echo-out: stop-start/echo-out transitions forbidden by default (listener rule)
 O1 overlap    : both decks at musical level >= 8 bars
 C1 groove     : master onset density never < 30% of local median for > 1 bar across a transition
 C2 outgoing   : outgoing deck > -10 dB rel. its body for the first half of the overlap
 S1 dead tail    : a deck keeps playing its own near-silent source tail (> 20 dB under its body) while audible in the mix,
                   or is loop-extended after such a tail (fade-to-silence then pop back in)
"""
import os,sys,json,re,subprocess,argparse,functools,numpy as np,soundfile as sf,librosa
from scipy.signal import butter,sosfiltfilt
ap=argparse.ArgumentParser();ap.add_argument('--src',default='/workspace/mixes/src2');ap.add_argument('--name',default='mix360')
ap.add_argument('--mp3',default='/workspace/mixes/dj-mix-03-60.mp3');ap.add_argument('--out',default=None);ap.add_argument('--png',action='store_true')
ap.add_argument('--nudge',default='nudge60.json');ap.add_argument('--skip-decks',action='store_true')
a=ap.parse_args();OUT=a.out or f'{a.src}/guard_{a.name}';os.makedirs(OUT,exist_ok=True)
os.environ['NUDGE']=a.nudge;sys.path.insert(0,os.path.join(os.path.dirname(os.path.abspath(__file__)),'tests'))
os.environ['MIX_SRC']=a.src;os.environ['MIX_NAME']=a.name;os.environ['MIX_MP3']=a.mp3;os.environ['MIX_WAV']=f'{a.src}/{a.name}_raw.wav'
import deckpair as P,checks as C
SR=44100;T=174.0;BEAT=60/T;BAR=4*BEAT;FR=22050/64;S16=BEAT/4  # phases folded on the 16th grid: every DnB hit sits on it, no kick/snare/2-step ambiguity
TH=dict(E1_db=6,E2_lufs=-35,N1_ms=10,N1_db=3,F1_ms=15,G1_jit_ms=8,G1_abs_ms=15,K1_steps=2,L1_db=3,P1_tp=-1.0,P1_dc=0.005,D1_ramp_db=3,S1_db=20)
M=json.load(open(f'{a.src}/{a.name}_meta.json'));D=M['decks'];TR=M['trans'];FX=M.get('fx',[])
ts=lambda s:f"{int(s//60)}:{int(s%60):02d}"
fails=[];info={}
def fail(chk,t0,t1,msg,**kw):fails.append(dict(check=chk,t=ts(t0),t_end=ts(t1),sec=round(t0,2),msg=msg,**kw))
# ---------- master loudness (ffmpeg ebur128: M=400 ms, S=3 s, every 100 ms) ----------
o=subprocess.run(['ffmpeg','-nostats','-i',a.mp3,'-af','ebur128=peak=true','-f','null','-'],capture_output=True,text=True).stderr
L=np.array([(float(x),float(m),float(s)) for x,m,s in re.findall(r't:\s*([\d.]+)\s+TARGET.*?M:\s*(-?[\d.]+|-inf)\s+S:\s*(-?[\d.]+)',o.replace('-inf','-120'))])
tL,Mo,St=L[:,0],L[:,1],L[:,2];dur=tL[-1]
summ=o[o.rfind('Summary'):];TP=float(re.search(r'Peak:\s+(-?[\d.]+)',summ.split('True peak')[1]).group(1));I=float(re.search(r'I:\s+(-?[\d.]+)',summ).group(1))
info['integrated_lufs']=I;info['true_peak_dbtp']=TP
# ---------- intentional breakdowns: a deck playing its own mid-track (non-tail) source section, or an echo/breakdown window
@functools.lru_cache(None)
def srcinfo(b):
  g=json.load(open(f'{a.src}/st/{b}.json'));al=np.array(g['bar']['all'],float);body=np.percentile(al,75)
  loud=np.where(al>body-20)[0];tail0=int(loud[-1])+1 if len(loud) else len(al)   # first bar of the record's own fade/silent tail
  return al,body,tail0
def active(bar):return [d for d in D if d['start_bar']<=bar<d['end_bar']]
def src_at(d,bar):return d['full_map'][int(bar-d['start_bar'])]
DECL={p['id']:p.get('breakdowns',[]) for p in M.get('plan',[])} if isinstance(M,dict) else {}
def intentional(bar):
  for t in TR:
    if 'echo' in t['tech'] and t['swap_bar']-1<=bar<=t['swap_bar']+16:return 'echo/breakdown window'
  for d in active(bar):
    k,st=src_at(d,bar)
    if st!='mix' or d['acap']:continue
    for lo,hi in DECL.get(d['id'],[]):   # breakdowns declared in the plan ("breakdowns": [[src_from,src_to]], max 4 bars)
      if lo<=k<=hi and hi-lo<=4:return f"{d['id']} declared breakdown (src bars {lo}-{hi})"
    al,body,tail0=srcinfo(d['id'])
    if k<tail0 and k<len(al) and al[k]>body-16 and C.gain_at(d,'gain',bar+.5)>0.5 and max(C.gain_at(d,'mid',bar+.5),C.gain_at(d,'high',bar+.5))>0.5:
      return f"{d['id']} own breakdown (src bar {k})"
  return None
# E1 / E2
med30=np.array([np.median(St[max(0,i-150):i+150]) for i in range(len(St))])
bad=(St<med30-TH['E1_db'])&(tL>8)&(tL<dur-8)
def runs(mask):
  i=0;n=len(mask)
  while i<n:
    if mask[i]:
      j=i
      while j<n and mask[j]:j+=1
      yield i,j;i=j
    else:i+=1
for i,j in runs(bad):
  bars=range(int(tL[i]/BAR),int(tL[j-1]/BAR)+1);why=[intentional(b) for b in bars]
  if all(why):continue
  k=i+int(np.argmin(St[i:j]));fail('E1',tL[i],tL[j-1],f'3s loudness {St[k]:.1f} LUFS is {med30[k]-St[k]:.1f} dB under the 30s median {med30[k]:.1f}',unexcused_bars=[f'{ts(b*BAR)}' for b,w in zip(bars,why) if not w][:8])
for i,j in runs((Mo<TH['E2_lufs'])&(tL>5)&(tL<dur-5)):fail('E2',tL[i],tL[j-1],f'momentary loudness down to {Mo[i:j].min():.1f} LUFS (near silence)')
# P1
if TP>TH['P1_tp']:fail('P1',0,dur,f'true peak {TP} dBTP')
x,_=sf.read(f'{a.src}/{a.name}_raw.wav',frames=SR*600,dtype='float32');dc=float(np.abs(x.mean(0)).max());info['dc']=dc
if dc>TH['P1_dc']:fail('P1',0,600,f'DC offset {dc:.4f}')
del x
# G1 master grid (raw mix onset, chunked)
on,_=C.onset();info['grid']=[]
ph=[];nb=int(dur/BAR)-2
for b in range(0,nb,2):
  seg=on[int(b*BAR*FR):int((b+2)*BAR*FR)];p=P.beat_phase(seg,fr=FR,per=S16,nb=2);ph.append((b,p))
ref=np.median([p for _,p in ph if p is not None]);prev=None
for b,p in ph:
  if p is None:prev=None;continue
  dv=abs(((p-ref+S16*500)%(S16*1000))-S16*500)
  if dv>TH['G1_abs_ms'] and not intentional(b):fail('G1',b*BAR,(b+2)*BAR,f'master beats {dv:.0f} ms off the global grid')
  if prev is not None and abs(p-prev)>TH['G1_jit_ms'] and min(abs(p-prev),S16*1000-abs(p-prev))>TH['G1_jit_ms'] and not intentional(b):fail('G1',b*BAR,(b+2)*BAR,f'beat-phase jump {p-prev:+.0f} ms between adjacent 2-bar windows')
  prev=p
# V1 vocal clash
for c in C.vocal_clashes():
  if not c['whitelisted'] and c['bars']>=1:fail('V1',0,0,f"{c['a']} & {c['b']} both singing {c['bars']} bars from {c['t']}",t_hint=c['t'])
# K1 keys
K=C.keys()
def cam_dist(x,y):
  na,la=int(x[:-1]),x[-1];nb_,lb=int(y[:-1]),y[-1];d=min((na-nb_)%12,(nb_-na)%12);return d+(0 if la==lb else 1) if d else (0 if la==lb else 1)
# ---------- per transition / per deck (decks rendered alone) ----------
@functools.lru_cache(maxsize=3)
def render(i):return P._render(D[i])
def bar_seg(y,d,bar,n=1):
  i=int(round((bar-d['start_bar'])*BAR*SR));return y[max(0,i):i+int(n*BAR*SR)]
db=lambda s:20*np.log10(np.sqrt(np.mean(s**2))+1e-9) if len(s) else -120
LP=butter(4,120,'low',fs=SR,output='sos')
def penv(seg):return P.snare_env(seg) if len(seg)>2048 else np.zeros(4)
TRS=[]
for ti,t in enumerate(TR):
  ia=max(i for i,d in enumerate(D) if d['id']==t['a'] and d['start_bar']<t['start_bar']+1 and not d['acap'])
  ib=[i for i,d in enumerate(D) if d['id']==t['b'] and abs(d['start_bar']-t['start_bar'])<1e-6][0]
  A,B=D[ia],D[ib];ya,yb=render(ia),render(ib);echo='echo' in t['tech']
  s=int(t['start_bar']);sw=int(t['swap_bar']);e=int(min(A['end_bar'],max(t['end_bar'],sw+1)))
  rows=[];refA=np.median([db(bar_seg(ya,A,b)) for b in range(max(int(A['start_bar']),s-8),s)] or [-20])
  for b in range(s-4,max(e,sw+8)+1):
    sa=bar_seg(ya,A,b) if A['start_bar']<=b<A['end_bar'] else np.zeros(0);sb=bar_seg(yb,B,b) if B['start_bar']<=b<B['end_bar'] else np.zeros(0)
    la,lb=db(sa),db(sb);r=dict(bar=b,t=ts(b*BAR),A=round(la,1),B=round(lb,1))
    if len(sa)>1000 and len(sb)>1000 and la>refA-14 and lb>refA-14 and abs(la-lb)<14:
      pa,pb=P.beat_phase(penv(sa),per=S16),P.beat_phase(penv(sb),per=S16)
      if pa is not None and pb is not None:
        r['flam_ms']=round(abs(((pa-pb+S16*500)%(S16*1000))-S16*500),1)
        if r['flam_ms']>TH['F1_ms']:fail('F1',b*BAR,(b+1)*BAR,f"{t['a']} vs {t['b']} beats {r['flam_ms']} ms apart",trans=ti)
      n=min(len(sa),len(sb));sa_,sb_=sosfiltfilt(LP,sa[:n]),sosfiltfilt(LP,sb[:n]);lsa,lsb,lsum=db(sa_),db(sb_),db(sa_+sb_)
      r.update(subA=round(lsa,1),subB=round(lsb,1),subSum=round(lsum,1))
      if lsum>max(lsa,lsb)+TH['L1_db']:fail('L1',b*BAR,(b+1)*BAR,f'sub sum {lsum:.1f} dB is {lsum-max(lsa,lsb):.1f} dB over the louder deck',trans=ti)
      if lsa>la-6 and lsb>lb-6 and min(lsa,lsb)>refA-12:fail('L1',b*BAR,(b+1)*BAR,'both decks carry full bass at once',trans=ti)
    # S1 dead tail of the outgoing deck
    if A['start_bar']<=b<A['end_bar']:
      k,stm=src_at(A,b);al,body,tail0=srcinfo(A['id'])
      if stm=='mix' and k>=tail0 and k<len(al) and al[k]<body-TH['S1_db']:r['A_tail']=True
    rows.append(r)
  tail=[r for r in rows if r.get('A_tail')]
  if tail:
    later=[r for r in rows if r['bar']>tail[-1]['bar'] and r['A']>min(x['A'] for x in tail)+10]
    fail('S1',tail[0]['bar']*BAR,tail[-1]['bar']*BAR+BAR,f"outgoing {t['a']} plays its own fade/silent tail during the transition"+(f"; then its loop pops back in at {later[0]['t']}" if later else ''),trans=ti)
  # K1
  ka,kb=K.get(t['a']),K.get(t['b']);harm=sum(1 for r in rows if 'flam_ms' in r or ('A' in r and r['A']>refA-14 and r['B']>refA-14))
  if ka and kb:
    dist=cam_dist(ka,kb)
    if dist>TH['K1_steps'] and not echo and harm>2:fail('K1',s*BAR,e*BAR,f'{ka}->{kb} ({dist} steps) over {harm} overlapping bars',trans=ti)
  # N1 entry: incoming first audible beats on grid + master level step at entry
  ent=next((r['bar'] for r in rows if r['B']>refA-24),None)
  if ent is not None:
    pb=P.beat_phase(penv(bar_seg(yb,B,ent,2)),per=S16,nb=2)
    if pb is not None and abs(pb)>TH['N1_ms']:fail('N1',ent*BAR,(ent+2)*BAR,f"{t['b']} enters {pb:+.0f} ms off the grid",trans=ti)
  for at in [B['start_bar']*BAR]+([sw*BAR] if not echo else []):
    i=np.searchsorted(tL,at);pre=np.median(Mo[max(0,i-8):i]);post=np.median(Mo[i+2:i+10])
    if abs(post-pre)>TH['N1_db'] and not (echo and post>pre):fail('N1',at,at+1,f'master level step {post-pre:+.1f} dB at {"entry" if at==B["start_bar"]*BAR else "bass swap"}',trans=ti)
  # X1 listener rule: no echo-out / stop-start transitions (unless the plan step says allow_echo)
  step=next((p for p in M['plan'] if p['id']==t['b']),{})
  if echo and not step.get('allow_echo'):fail('X1',s*BAR,(sw+4)*BAR,f"{t['a']} -> {t['b']} is an echo-out/stop-start ('{t['tech'][:40]}'), not a blend",trans=ti)
  # O1 real overlap: both decks at musical level (within 12 dB of the outgoing body) for >= 8 bars
  both=sum(1 for r in rows if r['A']>refA-12 and r['B']>refA-12)
  if both<8:fail('O1',s*BAR,e*BAR,f'only {both} bars with both decks audible at musical level (need >= 8)',trans=ti)
  # C2 outgoing groove: outgoing deck > -10 dB rel. its body for the first half of the overlap
  half=[r for r in rows if s<=r['bar']<(s+max(e,sw))/2]
  low=[r for r in half if r['A']<refA-10]
  if low:fail('C2',low[0]['bar']*BAR,low[-1]['bar']*BAR+BAR,f"outgoing {t['a']} {min(r['A'] for r in low)-refA:+.1f} dB under its body in the first half of the overlap",trans=ti)
  # C1 continuous groove: master onset density never collapses for > 1 bar across the transition
  seg=on[int((s-4)*BAR*FR):int((max(e,sw)+4)*BAR*FR)];nbt=len(seg)//int(BEAT*FR)
  if nbt>8:
    pb_=np.array([seg[k*int(BEAT*FR):(k+1)*int(BEAT*FR)].mean() for k in range(nbt)]);medb=np.median(pb_);lowb=pb_<0.3*medb;k=0
    while k<nbt:
      if lowb[k]:
        j=k
        while j<nbt and lowb[j]:j+=1
        if j-k>4:fail('C1',(s-4)*BAR+k*BEAT,(s-4)*BAR+j*BEAT,f'groove collapses for {(j-k)/4:.1f} bars (onset density < 30% of local median)',trans=ti)
        k=j
      else:k+=1
  TRS.append(dict(i=ti,t=ts(s*BAR),swap=ts(sw*BAR),a=t['a'],b=t['b'],tech=t['tech'],keys=f'{ka}->{kb}',rows=rows))
# D1 dropped drop (every deck drop)
for i,d in enumerate(D):
  if d['drop_bar'] is None or d['acap'] or i==0:continue
  dr=d['drop_bar'];fx=[f for f in FX if f[0].startswith(('riser','roll')) and abs(f[1]-dr)<=1 and f[2]>0]
  hpf=any(dr-9<=p[0]<=dr and p[1]>100 for p in d['auto'].get('hpf',[]))
  i0,i1=np.searchsorted(tL,(dr-8)*BAR),np.searchsorted(tL,dr*BAR-0.3);ramp=St[i1]-St[i0]
  if not (fx or hpf or ramp>=TH['D1_ramp_db'] or any('echo' in t['tech'] and abs(t['swap_bar']-dr)<=24 and t['b']==d['id'] for t in TR)):
    fail('D1',dr*BAR,dr*BAR+1,f"{d['id']} drop with no build (ramp {ramp:+.1f} dB, no riser/HPF)")
# S1 for any deck (within-track): audible near-silent tail followed by a loop re-entry
for i,d in enumerate(D):
  if d['acap']:continue
  al,body,tail0=srcinfo(d['id']);fm=d['full_map']
  for j in range(1,len(fm)):
    if fm[j][1]!='mix' and fm[j-1][1]=='mix' and fm[j-1][0]>=tail0:
      b=d['start_bar']+j
      if not any(f['check']=='S1' and abs(f['sec']-b*BAR)<60 for f in fails):fail('S1',b*BAR-4*BAR,b*BAR,f"{d['id']} faded through its own silent tail, then loop-extension re-enters",deck=i)
# ---------- report ----------
fails.sort(key=lambda f:f['sec']);by={}
for f in fails:by.setdefault(f['check'],0);by[f['check']]+=1
rep=dict(mix=a.name,mp3=a.mp3,thresholds=TH,info=info,n_fail=len(fails),by_check=by,failures=fails,
  transitions=[{k:v for k,v in t.items() if k!='rows'}|dict(flam_max=max([r.get('flam_ms',0) for r in t['rows']]),fails=[f['check'] for f in fails if f.get('trans')==t['i']]) for t in TRS])
json.dump(rep,open(f'{OUT}/guardrails.json','w'),indent=1,default=float)
json.dump(TRS,open(f'{OUT}/transitions_rows.json','w'),default=float)
# ---------- PNG strips ----------
if a.png:
  import matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
  def strip(t0,t1,title,path,decks):
    raw,_=sf.read(f'{a.src}/{a.name}_raw.wav',start=int(t0*SR),frames=int((t1-t0)*SR),dtype='float32');m=raw.mean(1)
    fig,ax=plt.subplots(6,1,figsize=(16,13),sharex=True);tt=t0+np.arange(len(m))/SR
    for k,(nm,y,d) in enumerate(decks[:2]):
      i0=int(round((t0-d['start_bar']*BAR)*SR));seg=np.zeros(len(m),np.float32);s0=max(0,-i0);src=y[max(0,i0):max(0,i0)+len(m)-s0];seg[s0:s0+len(src)]=src
      ax[k].plot(tt[::50],seg[::50],lw=.4,color='C%d'%k);ax[k].set_ylabel(nm[:12]);ax[k].set_ylim(-1,1)
    ax[2].plot(tt[::50],m[::50],lw=.4,color='k');ax[2].set_ylabel('master')
    for g in np.arange(np.ceil(t0/BEAT)*BEAT,t1,BEAT):
      for q in ax[:3]:q.axvline(g,color='r' if abs((g/BAR)-round(g/BAR))<1e-3 else '0.85',lw=.5 if abs((g/BAR)-round(g/BAR))<1e-3 else .2,zorder=0)
    i0,i1=np.searchsorted(tL,t0),np.searchsorted(tL,t1);ax[3].plot(tL[i0:i1],Mo[i0:i1],lw=.6,label='M 400ms');ax[3].plot(tL[i0:i1],St[i0:i1],lw=1.2,label='S 3s');ax[3].plot(tL[i0:i1],med30[i0:i1]-6,'r--',lw=.8,label='30s median-6');ax[3].axhline(-35,color='m',lw=.6);ax[3].set_ylabel('LUFS');ax[3].legend(fontsize=7,loc='lower left');ax[3].set_ylim(-45,-5)
    lo=sosfiltfilt(LP,m);hop=int(0.05*SR);n=len(lo)//hop;ax[4].plot(t0+np.arange(n)*0.05,20*np.log10(np.sqrt((lo[:n*hop].reshape(n,hop)**2).mean(1))+1e-9),lw=.6);ax[4].set_ylabel('sub<120Hz dB')
    y22=librosa.resample(m,orig_sr=SR,target_sr=22050);ch=librosa.feature.chroma_cqt(y=y22,sr=22050,hop_length=2048)
    ax[5].imshow(ch,aspect='auto',origin='lower',extent=[t0,t1,0,12],cmap='magma');ax[5].set_yticks(np.arange(12)+.5);ax[5].set_yticklabels('C C# D D# E F F# G G# A A# B'.split(),fontsize=6);ax[5].set_ylabel('chroma')
    for f in fails:
      if t0<=f['sec']<=t1:
        for q in ax[:5]:q.axvspan(f['sec'],max(f['sec']+0.3,BAR*0+ (lambda s:int(s.split(':')[0])*60+int(s.split(':')[1]))(f['t_end'])+1),color='red',alpha=.12)
        ax[0].text(f['sec'],0.85,f['check'],color='red',fontsize=8)
    ax[-1].set_xticks(np.arange(np.ceil(t0/10)*10,t1,10));ax[-1].set_xticklabels([ts(v) for v in np.arange(np.ceil(t0/10)*10,t1,10)],fontsize=7)
    fig.suptitle(title,fontsize=10);fig.tight_layout();fig.savefig(path,dpi=80);plt.close(fig)
  for t in TRS:
    tr=TR[t['i']];ia=max(i for i,d in enumerate(D) if d['id']==tr['a'] and d['start_bar']<tr['start_bar']+1 and not d['acap']);ib=[i for i,d in enumerate(D) if d['id']==tr['b'] and abs(d['start_bar']-tr['start_bar'])<1e-6][0]
    t0=max(0,(tr['start_bar']-8)*BAR);t1=min(dur,(max(tr['end_bar'],D[ia]['end_bar'])+8)*BAR)
    fl=[f['check'] for f in fails if f.get('trans')==t['i'] or t0<=f['sec']<=t1]
    strip(t0,t1,f"#{t['i']} {t['t']} {tr['a']} -> {tr['b']} | {tr['tech']} | keys {t['keys']} | FAIL {sorted(set(fl)) or 'none'}",f"{OUT}/trans_{t['i']:02d}_{t['t'].replace(':','')}.png",[(tr['a'],render(ia),D[ia]),(tr['b'],render(ib),D[ib])])
print(json.dumps(dict(n_fail=len(fails),by_check=by),indent=None))
for f in fails:print(f"FAIL {f['check']} {f['t']}-{f['t_end']} {f['msg']}")
sys.exit(1 if fails else 0)
