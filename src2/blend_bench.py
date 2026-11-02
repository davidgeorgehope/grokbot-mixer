"""Blend bench (decision_design.md step 1, 2026-11-01): generate -> render -> verify -> pick, per blend, standalone.
For each pair the listener rated (plus the Mix 06 see-saw-flagged pairs) build ~10 diverse candidates (families below), render a snippet
(PRE bars before the blend + blend + POST bars after) with the real engine (mix_simple.py --dry for the plan, engine.render_deck for
audio, ../src/master.sh with gain 9.3: mastering unchanged), time it, measure the blend on the rendered decks, and score candidates
with a small Bradley-Terry model fitted to the listener's ratings, starting from hand weights (strong L2 pull back to them).
Only two hard rejects (listener: intolerable): abrupt outgoing fade, beat train-wreck. Everything else is a feature.
Does NOT touch plan_search.py. Usage: python3 blend_bench.py [--jobs 4] [--keep-ab]"""
import json,os,sys,time,subprocess,copy,shutil,itertools
import numpy as np
HERE=os.path.dirname(os.path.abspath(__file__));ROOT=os.path.dirname(HERE)
SCR=os.environ.get('BB_SCRATCH','/tmp/blend_bench');OUTJ=f'{ROOT}/eval/blend_bench_results.json';ABDIR=f'{ROOT}/deliver/ab'
PRE,POST,GAIN=8,8,'9.3'
FEATS=['seesaw','lull','fade_step','flam','beat_off','dissonance','vocal','pro_shape','loop','struct']
W0=np.array([1.0,0.3,0.3,0.3,2.0,5.0,0.1,0.5,0.3,3.0])  # hand prior: cost = W.f (higher = worse)
LAM=float(os.environ.get('BB_LAM',1.0))
RENV={'mix05n_meta.json':{'FADE':'lin','BASS_SWAP_BARS':'2'}}  # Mix 05n was rendered before FADE=tail and the 4-bar swap (2026-10-31)
RATED_META={'06':'mix06i12_meta.json','mix05n':'mix05n_meta.json'}
EXTRA=[('rpIpJQ7ujzc>5196v8VY1LI','mix06i12_meta.json'),('4WY9J_yXj8M>zGBn-IJ1isg','mix06i12_meta.json')]  # Mix 06 W1-flagged, unrated

def rated_pairs():
  """latest rating per pair from ratings.jsonl, with the window the engine actually used (from that mix's meta)"""
  R={}
  for l in open(f'{ROOT}/ratings.jsonl'):
    r=json.loads(l)
    if 'pair' in r and r.get('mix') in RATED_META:R[r['pair']]=(r['rating'],RATED_META[r['mix']],r.get('t'))
  out=[]
  for k,(rt,mf,t) in R.items():out.append(dict(pair=k,rating=rt,win=_win(k,mf),meta=mf,t=t))
  for k,mf in EXTRA:out.append(dict(pair=k,rating=None,win=_win(k,mf),meta=mf,t=None))
  return out
def _win(pair,mf):
  a,b=pair.split('>');M=json.load(open(f'{HERE}/{mf}'));return next(p['out_win'] for p in M['plan'] if p['id']==a)

def sh(cmd,env=None,cwd=HERE):
  e=dict(os.environ);e.update(env or {});r=subprocess.run(cmd,shell=True,cwd=cwd,env=e,capture_output=True,text=True)
  if r.returncode:raise RuntimeError(f'{cmd}: {r.stderr[-400:]}')
  return r.stdout
def plan2(a,b,win=None):
  p=[{"id":a,"kw":{"pre":16,"build":True},"tech":"first"},{"id":b,"kw":{"pre":16,"build":True},"tech":"blend"}]
  if win:p[0]['out_win']=win
  return p
def cands_for(a,b,tag):
  f=f'{SCR}/{tag}_plan.json';json.dump(plan2(a,b),open(f,'w'));sh(f'python3 mix_simple.py --plan {f} --out {SCR}/{tag}',dict(DUMP_CANDS=f'{SCR}/{tag}_c.json'))
  return json.load(open(f'{SCR}/{tag}_c.json'))
def families(cs,rated_win,renv={}):
  """one candidate per family, best (lowest engine cost) first; diversity = different families, not neighbouring cue bars"""
  def best(pred):
    m=[c for c in cs if pred(c['win'])];return min(m,key=lambda c:c['cost'])['win'] if m else None
  F={}
  F['nat_long']=best(lambda w:w[0]=='n' and w[4]>=32);F['nat_short']=best(lambda w:w[0]=='n' and w[4]==16)
  F['out_loop']=best(lambda w:w[0]=='la');F['lx_beat']=best(lambda w:w[0]=='lx');F['in_loop']=best(lambda w:w[0]=='lb')
  nl=F['nat_long']
  if nl:
    same=sorted({c['win'][3] for c in cs if c['win'][0]=='n' and c['win'][1]==nl[1] and c['win'][4]==nl[4]})
    if len(same)>1:
      if same[0]!=nl[3]:F['cue_early']=[nl[0],nl[1],nl[2],same[0],nl[4]]
      if same[-1]!=nl[3]:F['cue_late']=[nl[0],nl[1],nl[2],same[-1],nl[4]]
  C=[dict(fam=k,win=w,env={}) for k,w in F.items() if w]
  if nl:
    C+=[dict(fam='swap_early',win=nl,env={'SWAP_POS':'0.21'}),dict(fam='swap_late',win=nl,env={'SWAP_POS':'0.6'}),dict(fam='sneak_in',win=nl,env={},sneak=True)]
  for c in C:c['is_rated']=bool(rated_win) and not renv and c['win']==rated_win and not c['env'] and not c.get('sneak')
  if rated_win and not any(c['is_rated'] for c in C):C.append(dict(fam='rated',win=rated_win,env=dict(renv),is_rated=True))  # rendered with the engine settings the listener heard
  return C

def sneak(M):
  """Wilkinson-style (eval/control_curves: incoming ~-15 dB with hats up for ~30 bars, then up + bass swap): crossfader x creeps
  0->0.11 (incoming -15 dB) over the first 60% of the blend, then 0.11->1; bass/high lanes shifted to 75% of the blend."""
  from engine import BAR
  t=M['trans'][0];s,e=t['start_bar'],t['end_bar'];X=e-s;xs=[]
  for k in range(int(X*4)+1):
    u=k/(X*4);x=0.11*u/0.6 if u<0.6 else 0.11+0.89*(u-0.6)/0.4;xs.append([s+k/4,round(x,5)])
  t['xfader']=xs;A,B=M['decks'];gA=lambda x:float(np.cos(x*np.pi/2));gB=lambda x:float(np.sin(x*np.pi/2))
  A['auto']['gain']=[[p,gA(x)] for p,x in xs];B['auto']['gain']=[[p,gB(x)] for p,x in xs]
  sw=np.mean(t['bass_swap']) if t.get('bass_swap') else t['swap_bar'];d=s+0.75*X-sw
  for D in (A,B):
    for lane in ('low','high'):
      if D['auto'].get(lane):D['auto'][lane]=[[p+d,g] for p,g in D['auto'][lane]]
  return M

def render(c,a,b,tag):
  """real engine: dry plan -> crop decks to the snippet -> engine.render_deck per deck -> sum -> master.sh (unchanged)"""
  import soundfile as sf,engine
  from engine import BS,SR
  t0=time.time();f=f'{SCR}/{tag}_plan.json';json.dump(plan2(a,b,c['win']),open(f,'w'))
  sh(f'python3 mix_simple.py --plan {f} --out {SCR}/{tag} --dry',c['env'])
  M=json.load(open(f'{SCR}/{tag}_dry_meta.json'))
  if c.get('sneak'):M=sneak(M)
  t=M['trans'][0];A=M['decks'][0];lx=any(s=='beat' for _,s in A['full_map'])
  pre=PRE+(int(A.get('lx_xf',2))+8 if lx else 0)
  s0,s1=int(t['start_bar'])-pre,int(t['end_bar'])+POST;n=int(round((s1-s0)*BS));dk=[]
  for d in M['decks']:
    j0=max(0,s0-d['start_bar']);j1=min(len(d['full_map']),s1-d['start_bar']);dd=copy.deepcopy(d)
    if d is A and lx:  # keep the lx switch index right: render from the beat switch's fade start
      pass
    dd['full_map']=d['full_map'][j0:j1];dd['start_bar']=d['start_bar']+j0;
    if dd.get('ib'):dd['ib']=dict(dd['ib'],k0=dd['ib']['k0']-j0,k1=dd['ib']['k1']-j0)  # beatmelody ib: deck-relative indices follow the crop
    y=engine.render_deck(dd)
    o=int(round((dd['start_bar']-s0)*BS));Y=np.zeros((n+int(8*BS),2),np.float32);m=min(len(y),len(Y)-o);Y[o:o+m]=y[:m];dk.append(Y[:n])
  mix=dk[0]+dk[1];raw=f'{SCR}/{tag}_raw.wav';sf.write(raw,mix,SR,subtype='FLOAT')
  sh(f'bash ../src/master.sh {raw} {SCR}/{tag}.mp3 {GAIN} {SCR}/{tag}_master.wav')
  dt=time.time()-t0;c.update(render_s=round(dt,2),mp3=f'{SCR}/{tag}.mp3',snip=dict(s0=s0,start=int(t['start_bar']),end=int(t['end_bar']),pre=pre),
    vocal_clash_bars=float(t.get('vocal_clash_bars') or 0),tech=t['tech'],notes=t.get('notes'))
  import sections;SA,SB=sections.get(a),sections.get(b);Bd=M['decks'][1];j=int(t['end_bar']-Bd['start_bar'])
  inb=Bd['full_map'][j][0] if 0<=j<len(Bd['full_map']) else -99;ea=c['win'][1]
  c['struct']=round(min(abs(inb-SB['drop1']),8)/8*0.5+min(abs(ea-SA['music_end']),32)/32*0.5,3)  # 0 = outro over intro: outgoing to its music end, incoming drop lands at blend end (gold rule / engine STRUCT)
  for k in list(engine._cache):engine._cache[k]['st'].clear()
  return dk,M

def bar_db(y,BS,nb):
  m=y.mean(1);return np.array([10*np.log10(np.mean(m[int(k*BS):int((k+1)*BS)]**2)+1e-12) for k in range(nb)])
def band_db(y,BS,nb,kind,fc):
  from scipy.signal import butter,sosfiltfilt
  return bar_db(sosfiltfilt(butter(4,fc,kind,fs=44100,output='sos'),y,axis=0),BS,nb)
def flam_ms(a,b):
  """beat-phase offset between the decks (each alone): lag of max xcorr of kick-band onset envelopes, +-40 ms"""
  import librosa
  from scipy.signal import butter,sosfiltfilt
  sos=butter(4,120,'low',fs=44100,output='sos');hop=64
  oa=librosa.onset.onset_strength(y=sosfiltfilt(sos,a.mean(1)),sr=44100,hop_length=hop);ob=librosa.onset.onset_strength(y=sosfiltfilt(sos,b.mean(1)),sr=44100,hop_length=hop)
  L=int(0.04*44100/hop);n=min(len(oa),len(ob));oa,ob=oa[:n]-oa[:n].mean(),ob[:n]-ob[:n].mean()
  xc=[np.dot(oa[max(0,k):n+min(0,k)],ob[max(0,-k):n-max(0,k)]) for k in range(-L,L+1)];return abs(int(np.argmax(xc))-L)*hop/44.1
def measure(c,dk,M):
  """measured-audio checks on the rendered decks (not predicted levels)"""
  import seesaw as SS,ears
  from engine import BS
  A,B=dk;sn=c['snip'];nb=int(round(len(A)/BS));b0,b1=sn['start']-sn['s0'],sn['end']-sn['s0']
  a,b=bar_db(A,BS,nb),bar_db(B,BS,nb);s=10*np.log10(10**(a/10)+10**(b/10));ref=float(np.median(np.r_[s[:b0],s[b1:]]))
  ab,bb,sb=a[b0:b1],b[b0:b1],s[b0:b1]
  rise=float(np.max(np.diff(ab)));wob=SS.reversals(sb,SS.WOB_DB);da,db_=np.diff(ab),np.diff(bb);ok=(ab[1:]>-60)&(bb[1:]>-60)
  r=float(np.corrcoef(da[ok],db_[ok])[0,1]) if ok.sum()>4 and da[ok].std()>0 and db_[ok].std()>0 else 0.0
  w1=[k for k,v in dict(OUT_RISE=rise>SS.OUT_RISE_DB,WOBBLE=wob>=SS.WOB_N,ANTI=r<=SS.ANTI_R and da[ok].std()>=SS.ANTI_DB and db_[ok].std()>=SS.ANTI_DB).items() if v]
  seesaw=max(0,rise-2)+max(0,wob-1)+3*max(0,-r-0.3)
  lull=max(0.0,ref-float(np.min(sb))-3)
  im=int(np.argmin(sb));post=s[b1:b1+4]
  if lull>0 and im>=len(sb)//2 and len(post) and float(np.max(post))>=ref-1 and float(np.max(b[b1-1:b1+4]))-float(bb[im])>=6:lull=0.0  # the listener 5/5 gold Lilies>Just Hold On: a dip that resolves into the incoming drop at blend end is tension, not a hole
  aa=np.maximum(a[:b1],ref-40);drops=[aa[k]-aa[k+1] for k in range(max(0,b0-8),b1-1) if aa[k]>ref-25];fade=max(drops+[0])  # inside the blend only: the deck's end at the blend's last bar is the crossfader at 0, not a fade
  aref=float(np.median(a[max(0,b0-8):b0]));i3=next((k for k in range(b0,len(a)) if a[k]<aref-3),b1);i20=next((k for k in range(i3,len(a)) if a[k]<aref-20),len(a))
  lo=band_db(A,BS,nb,'low',150);hi=band_db(A,BS,nb,'high',2000);lref,href=np.median(lo[max(0,b0-8):b0]),np.median(hi[max(0,b0-8):b0])
  lout=next((k for k in range(b0,len(lo)) if lo[k]<lref-6),b1);hout=next((k for k in range(b0,len(hi)) if hi[k]<href-6),b1)
  pro=abs((i20-i3)-4.5)/4.5+0.5*(hout<lout)  # pros: outgoing -3->-20 dB over ~4.5 bars; highs leave after the bass
  BSi=int(BS);fl=[];bo=[];di=[]
  pa,pb=ears.pattern(A[b0*BSi:b1*BSi]),ears.pattern(B[b0*BSi:b1*BSi])
  for k in range(min(len(pa),len(pb))):
    if a[b0+k]>ref-20 and b[b0+k]>ref-20:bo.append(max(0,ears.beat_off(pa[k],pb[k])))
  ca,cb=ears.chroma_beats(A[b0*BSi:b1*BSi]),ears.chroma_beats(B[b0*BSi:b1*BSi])
  di=[ears.dissonance(ca[k],cb[k]) for k in range(min(len(ca),len(cb))) if a[b0+k//4]>ref-20 and b[b0+k//4]>ref-20]
  for k in range(b0,b1,4):
    if a[k]>ref-20 and b[k]>ref-20:fl.append(flam_ms(A[k*BSi:(k+4)*BSi],B[k*BSi:(k+4)*BSi]))
  f=dict(seesaw=seesaw,lull=lull,fade_step=max(0,fade-6),flam=max(0.0,float(np.median(fl))-8) if fl else 0.0,beat_off=float(np.mean(bo)) if bo else 0.0,
    dissonance=float(np.mean(di)) if di else 0.0,vocal=c['vocal_clash_bars'],pro_shape=pro,loop=float(c['win'][0] in('la','lb','ab','lx')),struct=c['struct'])
  hard=[]
  if fade>12:hard.append(f'abrupt outgoing fade {fade:.1f} dB/bar')
  if (fl and np.median(fl)>30) or (bo and np.mean(bo)>0.6):hard.append('beat train-wreck')
  c.update(feats={k:round(float(v),3) for k,v in f.items()},w1=w1,raw=dict(out_rise=round(rise,1),wobble=wob,anti_r=round(r,2),fade_db=round(fade,1),fade3to20=i20-i3,lull_db=round(ref-float(np.min(sb)),1)),hard=hard)

def fv(c):return np.array([c['feats'][k] for k in FEATS])
def bt_fit(P,w0=W0,lam=LAM,it=3000,lr=0.02):
  """pairwise logistic BT on cost differences: P = [(f_winner, f_loser)], P(w>l)=sigma(w.(f_l-f_w)); L2 pull to w0; w>=0"""
  w=np.array(w0,float)
  if not P:return w
  D=np.array([fl-fw for fw,fl in P]);sc=np.maximum(np.abs(D).max(0),1e-6)
  for _ in range(it):
    z=D@w;p=1/(1+np.exp(-np.clip(z,-30,30)));g=(-(D*(1-p)[:,None]).sum(0)+2*lam*(w-w0))/len(D)  # MAP: sum log-lik + lam*||w-w0||^2
    w=np.maximum(w-lr/(1+2*lam/len(D))*g/sc,0)
  return w
def cost(c,w):return float(w@fv(c))+(1e3 if c['hard'] else 0)

def train_pairs(R):
  """across rated blends: higher rating beats lower (the rated window's own render)"""
  rated=[(r['rating'],next(c for c in r['cands'] if c['is_rated']),r['pair']) for r in R if r['rating'] is not None and any(c['is_rated'] for c in r['cands'])]
  out=[(fv(x),fv(y),px,py) for (rx,x,px),(ry,y,py) in itertools.permutations(rated,2) if rx>ry]
  # blind A/B picks (ratings.jsonl type=ab, winner_fam/loser_fam): same-pair pairwise datapoints, weighted by strength (strong 3, normal 2, weak 1)
  for l in open(f'{ROOT}/ratings.jsonl'):
    q=json.loads(l)
    if q.get('type')!='ab' or 'winner_fam' not in q:continue
    r=next((r for r in R if r['pair']==q['pair']),None)
    if not r:continue
    pick=lambda f:next((c for c in r['cands'] if (c['is_rated'] if f=='rated' else c['fam']==f)),None)
    x,y=pick(q['winner_fam']),pick(q['loser_fam'])
    if x and y:out+=[(fv(x),fv(y),q['pair'],q['pair'])]*int(q.get('weight',2))
  return out

def main():
  jobs=int(sys.argv[sys.argv.index('--jobs')+1]) if '--jobs' in sys.argv else 4
  os.makedirs(SCR,exist_ok=True);os.chdir(HERE);sh('python3 restore_audio.py >/dev/null')
  R=rated_pairs();T0=time.time();todo=[]
  for i,r in enumerate(R):
    a,b=r['pair'].split('>');r['cands']=families(cands_for(a,b,f'p{i}'),r['win'],RENV.get(r['meta'],{}))
    for j,c in enumerate(r['cands']):todo.append((i,j,a,b))
  from concurrent.futures import ProcessPoolExecutor
  with ProcessPoolExecutor(jobs) as ex:
    res=list(ex.map(_job,[(R[i]['cands'][j],a,b,f'p{i}c{j}') for i,j,a,b in todo]))
  for (i,j,_,_),c in zip(todo,res):R[i]['cands'][j]=c
  wall=time.time()-T0
  import hashlib
  for r in R:  # identical audio (e.g. a 16-bar 'lb' loop of phrase q == playing q..q+16 straight; swap moves snapped to the same bar) counts once
    seen={};keep=[]
    for c in r['cands']:
      h=hashlib.md5(open(c['mp3'],'rb').read()).hexdigest()
      if h in seen:seen[h].setdefault('same_as',[]).append(c['fam']);seen[h]['is_rated']|=c['is_rated'];continue
      seen[h]=c;keep.append(c)
    r['cands']=keep
  TP=train_pairs(R);w=bt_fit([(x,y) for x,y,_,_ in TP])
  loo=[];  # leave-one-comparison-out
  for k in range(len(TP)):
    wk=bt_fit([(x,y) for m,(x,y,_,_) in enumerate(TP) if m!=k]);x,y,px,py=TP[k];loo.append(dict(win=px,lose=py,ok=bool(wk@x<wk@y)))
  loo_prior=[bool(W0@x<W0@y) for x,y,_,_ in TP]
  for r in R:
    for c in r['cands']:c['cost']=round(cost(c,w),3)
    r['cands'].sort(key=lambda c:c['cost'])
    r['margin']=round(r['cands'][1]['cost']-r['cands'][0]['cost'],3) if len(r['cands'])>1 else None
  g=next(r for r in R if r['pair']=='j9AuFRpLk7U>cxS6yd0UAxw');rem=next(r for r in R if r['pair']=='sObzaBqaBRQ>q_cZZY0BehE')
  gold_top=bool(g['cands'][0]['is_rated']);gold_rank=next(k for k,c in enumerate(g['cands']) if c['is_rated'])+1
  rl=next(c for c in rem['cands'] if c['is_rated']);nat=[c for c in rem['cands'] if c['fam'] in('nat_long','nat_short')]
  rem_ok=bool(nat) and rl['cost']>min(c['cost'] for c in nat)
  rt=[c['render_s'] for r in R for c in r['cands']]
  out=dict(date=time.strftime('%Y-%m-%d %H:%M %Z'),feats=FEATS,w0=W0.tolist(),w=[round(float(x),4) for x in w],lam=LAM,
    n_train_pairs=len(TP),loo=loo,loo_acc=round(np.mean([l['ok'] for l in loo]),3) if loo else None,prior_acc=round(np.mean(loo_prior),3) if loo_prior else None,
    criteria=dict(gold_top=gold_top,gold_rank=gold_rank,remedy_loop_below_natural=rem_ok),render_s=dict(mean=round(np.mean(rt),2),median=round(np.median(rt),2),max=round(max(rt),2),n=len(rt),wall_s=round(wall,1),jobs=jobs),pairs=R)
  ab=make_ab(R);out['ab']=ab
  done={(q['pair'],frozenset((q['winner_fam'],q['loser_fam']))) for q in (json.loads(l) for l in open(f'{ROOT}/ratings.jsonl')) if q.get('type')=='ab' and 'winner_fam' in q}
  pend=[dict(a,status='pending') for a in ab if (a['pair'],frozenset((a['A']['fam'],a['B']['fam']))) not in done if a['margin'] is not None and a['margin']<float(os.environ.get('AB_NEAR',1.0))]
  json.dump(dict(date=out['date'],note='near-tied blend versions for the listener to A/B; engine already picked the best and flagged these, mix is not blocked',items=pend),open(f'{ABDIR}/pending.json','w'),indent=1,default=float)
  json.dump(out,open(OUTJ,'w'),indent=1,default=float)
  print(json.dumps({k:out[k] for k in ('w','n_train_pairs','loo_acc','prior_acc','criteria','render_s')},default=float));print('AB',json.dumps(ab,indent=1))
  for r in R:print(r['pair'],r['rating'],'margin',r['margin'],[(c['fam'],c['cost'],c['w1'],c['hard']) for c in r['cands']])
  if '--keep-scratch' not in sys.argv:shutil.rmtree(SCR,ignore_errors=True)
def _job(x):
  c,a,b,tag=x;f=f'{SCR}/{tag}_decks.npz';fc=f'{SCR}/{tag}_c.json'
  if os.environ.get('BB_REUSE') and os.path.exists(f) and os.path.exists(fc):c=json.load(open(fc));z=np.load(f);dk=[z['A'],z['B']];M=None
  else:dk,M=render(c,a,b,tag);np.savez(f,A=dk[0],B=dk[1]);json.dump(c,open(fc,'w'),default=float)
  measure(c,dk,M);return c
def make_ab(R,n=4):
  """the n most uncertain comparisons: smallest BT margin between the top two candidates of a pair"""
  os.makedirs(ABDIR,exist_ok=True)
  for f in os.listdir(ABDIR):os.remove(f'{ABDIR}/{f}')
  Q=[]  # 1) model disagrees with listener: a blend he rated >=4 that the model does not rank first -> his rated version vs the model's pick
  for r in R:
    rc=next((c for c in r['cands'] if c['is_rated']),None)
    if r['rating'] is not None and r['rating']>=4 and rc and r['cands'][0] is not rc:Q.append((r,r['cands'][0],rc,'model top vs your rated version'))
  for r in sorted([r for r in R if r['margin'] is not None],key=lambda r:r['margin']):  # 2) smallest BT margin between the top two
    if len(Q)>=n:break
    if not any(q[0] is r for q in Q):Q.append((r,r['cands'][0],r['cands'][1],'top two within margin'))
  ab=[]
  for k,(r,A,B,why) in enumerate(Q,1):
    nm=f"ab{k}_{r['pair'].replace('>','_to_')}"
    for s,c in (('A',A),('B',B)):shutil.copy(c['mp3'],f'{ABDIR}/{nm}_{s}.mp3')
    ab.append(dict(n=k,why=why,pair=r['pair'],rating=r['rating'],margin=round(B['cost']-A['cost'],3),A=dict(file=f'{ABDIR}/{nm}_A.mp3',fam=A['fam'],win=A['win'],cost=A['cost']),B=dict(file=f'{ABDIR}/{nm}_B.mp3',fam=B['fam'],win=B['win'],cost=B['cost'])))
  json.dump(ab,open(f'{ABDIR}/ab.json','w'),indent=1);return ab
if __name__=='__main__':main()
