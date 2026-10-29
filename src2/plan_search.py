"""Plan everything before rendering (additive to mix_simple.py; this file never renders audio).
  python3 plan_search.py table  --base plan.json           pairwise blend table for every analysed crate track -> pair_table.json (cached)
  python3 plan_search.py search --base plan.json --out p.json [--min 58 --max 62] [--exclude id,id]  (exclude = tracks a render proved unplaceable)   order + windows meeting every test target
  python3 plan_search.py predict <name>                    test metrics predicted from <name>_meta.json alone (no audio)
  python3 plan_search.py validate                          predicted vs rendered results for every mix with guard_<name>/guardrails.json
The chosen windows are written into the plan as 'out_win' so mix_simple renders exactly what was planned.
Run with the same scorer env as the render (SHORTPEN, BOTHPEN, DRUMPEN, VPEN, ...)."""
import sys,os,json,glob,time,math,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'../src/tests');os.environ.setdefault('MIX_SRC','.')
import checks as C
import pair_feats as PF
MELMAX=int(os.environ.get('MELMAX',8))      # max blend bars where both decks' melody/chord layer is above its own median (Bad To Me->Blame You 34:05, rated 1/5: 11; Parallel->Bad To Me 30:56, 5/5: 0)
MELPEN=float(os.environ.get('MELPEN',4))    # search cost per such bar, scaled by chord rub
DRIFTPEN=float(os.environ.get('DRIFTPEN',2))  # search cost per ms of median 16th-grid phase gap between the decks' source bars above 5 ms
SCORER_ENV=('XBARS','SWAP_POS','HEAVY','BASS_SWAP_BARS','DRUMPEN','SGPEN','VPEN','BOTHPEN','GAPPEN','CUEW','LW','SEAMPEN','RPEN','HOLE_DB','HOLEPEN','SEAMMAX','BOTHMIN','HARDPEN','SHORTPEN','LOOPPEN')
E4_DB,E4_BARS=10,12  # E4 on predicted (pre-master) levels: calibrated on 12 renders by `validate` (the master compresses dips, so 6 dB/8 bars in LUFS ~ 10 dB/12 bars here)
MIN_S=45/C.BAR      # E4 ignores the first/last 45 s

def _reset(name):
  C.NAME=name
  for f in(C.meta,C.decks):getattr(f,'cache_clear',lambda:None)()
def mix_levels(M):
  """predicted per-bar mix level (dB): power sum of every deck's source-bar level times its crossfader gain"""
  NB=int(max(d['end_bar'] for d in M['decks']));P=np.zeros(NB)
  for d in M['decks']:
    al=C.src_bars(d['id'])
    for i,(s,_) in enumerate(d['full_map']):
      j=int(d['start_bar'])+i
      if j<NB and s<len(al):P[j]+=C.gain_at(d,'gain',j+.5)**2*10**(al[s]/10)
  return 10*np.log10(np.maximum(P,1e-12))
def e4_runs(L):
  """guardrail E4 on predicted levels: 2-bar (~3 s) level > E4_DB under the whole-mix median for > E4_BARS bars, outside the first/last 45 s"""
  S=np.convolve(10**(L/10),np.ones(2)/2,'same');S=10*np.log10(np.maximum(S,1e-12));n=len(S);lo,hi=int(MIN_S),int(n-MIN_S)
  med=float(np.median(S[lo:hi]));bad=(S<med-E4_DB)&(np.arange(n)>=lo)&(np.arange(n)<hi);out=[];i=0
  while i<n:
    if bad[i]:
      j=i
      while j<n and bad[j]:j+=1
      if j-i>E4_BARS:out.append((i,j))
      i=j
    else:i+=1
  return out
def ts(b):s=b*C.BAR;return f'{int(s//60)}:{int(s%60):02d}'
def predict(name):
  """every meta-only test target, computed with the tests' own functions on the meta, plus a level-model E4"""
  _reset(name);import test_mix02_traits as T2,test_mix as TM;M=C.meta();D=M['decks']
  r=T2._drum_runs();n=len(r);K=C.keys()
  cov={d['id']:round(T2.body_coverage(d),2) for d in D if not d.get('acap')}
  def ok(f):
    try:f();return True
    except AssertionError:return False
  lens=[t['end_bar']-t['start_bar'] for t in M['trans'] if 'echo' not in t['tech']]
  keyclash=[(a['id'],b['id']) for a,b in zip(D,D[1:]) if not C.camelot_ok(K[a['id']],K[b['id']]) and C.harmonic_overlap(a,b)>2]
  e4=[(ts(i),j-i) for i,j in e4_runs(mix_levels(M))]
  p=dict(blends=n,bob16=sum(b>=16 for b,_,_ in r),beatless=sum(nn>x/2 for _,nn,x in r),x32=sum(x>=32 for x in lens),
    cov_mean=round(float(np.mean(list(cov.values()))),3),cov_min=min(cov.values()),cov_low=[k for k,v in cov.items() if v<0.5],
    drums_only_ok=ok(T2.test_no_long_drums_only_stretch),anchors_ok=ok(TM.test_anchor_tracks_long_enough),
    vocal_clash=[c for c in C.vocal_clashes() if not c['whitelisted'] and c['bars']>=1],key_clash=keyclash,E4=e4,
    len_min=round(max(d['end_bar'] for d in D)*C.BAR/60,2),drum_runs=[b for b,_,_ in r])
  p['tests']=dict(bob16=p['bob16']>=n/2,beatless=p['beatless']<=n/3,x32=p['x32']>=n/2,coverage=p['cov_mean']>=0.8 and p['cov_min']>=0.5,
    drums_only=p['drums_only_ok'],anchors=p['anchors_ok'],vocal=not p['vocal_clash'],keys=not keyclash,E4=not e4)
  p['all_ok']=all(p['tests'].values());return p

# ---------- pairwise blend table ----------
def scorer(base):
  """mix_simple's own window scorer (everything above its blend loop), loaded once: the table scores windows with the render's exact code"""
  src=open('mix_simple.py').read();sys.argv=['mix_simple.py','--plan',base,'--out','/dev/null']
  ns={'__name__':'mix_simple_scorer'};exec(compile(src[:src.index('LOOK=int(')],'mix_simple.py','exec'),ns);return ns
def windows(kind,e,p,ib,X):
  wa=[p+(k%16) for k in range(X)] if kind in('la','ab') else list(range(e-X,e))
  wb=[ib+(k%16) for k in range(X)] if kind in('lb','ab') else list(range(ib,ib+X));return wa,wb
def crate():
  K=C.keys();return sorted(b for b in (os.path.basename(f)[:-5] for f in glob.glob('st/*.json')) if b in K and glob.glob(f'st/{b}*.wav'))
def table_key(base):
  h=[os.environ.get(k) for k in SCORER_ENV]+[os.path.getmtime(f) for f in('mix_simple.py','cue_model.json','pair_feats.py')]
  return json.dumps([h,[(p['id'],p.get('anchor'),p.get('anchor_in'),p.get('out_max')) for p in json.load(open(base))],crate()],default=str)
def clash(fa,fb,wa,wb):
  """melodic + grid clash of one window, from the pair_feats per-bar features, over the bars where both crossfader gains are >= 0.38
  (the middle ~50% of an equal-power blend): mel = bars where both decks' harmonic layer is above that track's median, rub = mean chord rub on
  those bars, drift = median |16th-grid phase gap| (ms) on bars where both have a grid"""
  (ca,ea,pa),(cb,eb,pb)=fa,fb;X=len(wa);ma,mb=np.median(ea),np.median(eb);mel=0;rub=[];dr=[]
  for k,(sa,sb) in enumerate(zip(wa,wb)):
    x=(k+.5)/X
    if sa>=len(ca) or sb>=len(cb) or min(np.cos(x*np.pi/2),np.sin(x*np.pi/2))<0.38:continue
    if ea[sa]>ma and eb[sb]>mb:mel+=1;rub.append(PF.clash(ca[sa],cb[sb]))
    if not(np.isnan(pa[sa]) or np.isnan(pb[sb])):dr.append(abs(pa[sa]-pb[sb]))
  return dict(mel=mel,rub=round(float(np.mean(rub)),3) if rub else 0.0,drift=round(float(np.median(dr)),1) if dr else 0.0)
def table(base,path='pair_table.json',K=40):
  """every ordered pair of crate tracks: key compatibility, and for key-compatible pairs the K best windows (scored as if the outgoing
  track started at bar 0; search re-checks each window against the real start) with predicted beat-on-beat run, beatless bars, vocal clash
  bars, level dip, energy step, cue-model score and blend length. Cached; rebuilt when the scorer env, code, crate or anchors change."""
  key=table_key(base)
  if os.path.exists(path):
    T=json.load(open(path))
    if T['key']==key:return T
  import cue;CM=cue.load();ns=scorer(base);KE=C.keys();ids=crate();t0=time.time();tr={};pairs={};FT={b:PF.load(b) for b in ids}
  for b in ids:
    t,al,body,v,nb=ns['A_'](b);g=t['g']['bar']
    tr[b]=dict(key=KE[b],nb=nb,body=float(body),tail=int(ns['tail0'](al,body)),e_max=int(min(ns['tail0'](al,body),nb,ns['OUTMAX'].get(b,nb))//16*16),
      anchor=b in ns['ANCH'],cuef=cue.track_feats(g['all'],g['low'],g['hat']))
  for a in ids:
    for b in ids:
      if a==b:continue
      ok=bool(C.camelot_ok(KE[a],KE[b]));row=dict(key_ok=ok,keys=f'{KE[a]}->{KE[b]}',energy_step=round(tr[b]['body']-tr[a]['body'],1),wins=[])
      if ok:
        ns['ids'][:]=[a,b];dA,dB=ns['drums_on'](a),ns['drums_on'](b);alA,alB=ns['A_'](a)[1],ns['A_'](b)[1]
        for sc,kind,e,ib,r,X in ns['pair_cands'](0,0)[:K]:
          e,p=e if isinstance(e,tuple) else (e,None);wa,wb=windows(kind,e,p,ib,X)
          none=sum(not(xa<len(dA) and dA[xa]) and not(xb<len(dB) and dB[xb]) for xa,xb in zip(wa,wb))
          x=(np.arange(X)+.5)/X;lv=10*np.log10(np.cos(x*np.pi/2)**2*10**(alA[wa]/10)+np.sin(x*np.pi/2)**2*10**(alB[np.minimum(wb,len(alB)-1)]/10))
          row['wins'].append(dict(w=[kind,int(e),None if p is None else int(p),int(ib),int(X)],pen=round(float(r['pen']),1),bob=int(r['DT']),beatless=int(none),
            voc=int(r['V']),both=int(r['both']),L=int(r['L']),R=r['R'],dip=round(float(tr[a]['body']-lv.min()),1),lv=[round(float(x),1) for x in lv],cue=round(1-cue.pctl(CM,'out',tr[a]['cuef'],e),3),**clash(FT[a],FT[b],wa,wb)))
      pairs[f'{a}>{b}']=row
  for b in tr:tr[b].pop('cuef')
  T=dict(key=key,built_s=round(time.time()-t0,1),tracks=tr,pairs=pairs);json.dump(T,open(path,'w'));return T

# ---------- search over order + windows ----------
def _valid(t,w,ia):
  """can mix_simple pick window w for outgoing track t when t starts at bar ia (same limits as pair_cands)"""
  kind,e,p,ib,X=w;minlen=160 if t['anchor'] else 96-X;em=t['e_max']
  emin=max(ia+minlen,ia+int((em-ia)*0.5));emin+=(-emin)%16;emin=min(emin,em)
  if kind in('la','ab'):return e>=(max(ia+16,emin-X) if t['anchor'] else emin) and p>=max(ia,16)
  return e>=emin
def _deck(inn,e,p,Xout):
  """source-bar map of a deck: incoming spec inn=(kind,ib,Xin), plays to e, then loops phrase p for Xout bars"""
  k,ib,Xin=inn;m=[ib+(j%16) for j in range(Xin)]+list(range(ib+16,e)) if k in('lb','ab') else list(range(ib,e))
  return m+([p+(j%16) for j in range(Xout)] if p is not None else [])
class Crate:
  def __init__(s,T):
    s.T=T;s.tr=T['tracks'];s.al={b:C.src_bars(b) for b in s.tr};s.loud={b:set(np.where(a>np.percentile(a,75)-6)[0].tolist()) for b,a in s.al.items()}
    s.ref=float(np.median([np.median(a[:s.tr[b]['tail']]) for b,a in s.al.items()]))  # ~ the mix median level
  def close(s,b,m,lin,lout,at,end=1e9):
    """a finished deck starting at mix bar `at`, with the predicted mix levels of its incoming/outgoing blends:
    (coverage, longest run under the E4 line inside E4's window, seconds)"""
    cov=len(s.loud[b]&set(m))/max(1,len(s.loud[b]));al=s.al[b];run=best=0
    L=list(lin)+[al[x] if x<len(al) else -120 for x in m[len(lin):len(m)-len(lout)]]+list(lout)
    for j,l in enumerate(L):run=run+1 if MIN_S<=at+j<end-MIN_S and l<s.ref-E4_DB else 0;best=max(best,run)
    return cov,best,len(m)*C.BAR
def search(base,lo=58,hi=62,beam=300,BW=(0,60,200),fix_open=True,exclude=()):
  T=table(base);K=Crate(T);tr={b:t for b,t in K.tr.items() if b not in exclude};B=json.load(open(base));first=B[0]['id'] if fix_open else None;done=[];t0=time.time()
  LOB,HIB=lo*60/C.BAR,hi*60/C.BAR
  for bw in BW:
    starts=[first] if first else list(tr)
    S=[dict(seq=[b],inn=('n',0,0),lin=[],bl=[],cov=[],bars=0,cost=0.0) for b in starts]
    while S:
      nxt={}
      for st in S:
        a=st['seq'][-1];ia=st['inn'][1]+16 if st['inn'][0] in('lb','ab') else st['inn'][1]
        for b in tr:
          if b in st['seq']:continue
          row=T['pairs'][f'{a}>{b}']
          if not row['key_ok']:continue
          for w in row['wins']:
            kind,e,p,ib,X=w['w']
            if w['voc'] or w['both']<8 or w['R']<0.2 or w['mel']>MELMAX or not _valid(tr[a],w['w'],ia):continue
            m=_deck(st['inn'],e,p,X if p is not None else 0)
            cov,lull,sec=K.close(a,m,st['lin'],w['lv'],st['bars']-st['inn'][2])
            if cov<0.5 or lull>E4_BARS or (tr[a]['anchor'] and sec<C.MIN_ANCHOR_S):continue
            bars=st['bars']+len(m)-st['inn'][2]
            if bars>HIB:continue
            bl=st['bl']+[dict(a=a,b=b,**w)];cv=st['cov']+[cov]
            cost=st['cost']+w['pen']/100+bw*(w['bob']<16)+30*(X<32)+60*(w['beatless']>X/2)+50*max(0,0.85-cov)+MELPEN*w['mel']*w['rub']/0.25+DRIFTPEN*max(0,w['drift']-5)
            ns=dict(seq=st['seq']+[b],inn=(kind,ib,X),lin=w['lv'],bl=bl,cov=cv,bars=bars,cost=cost)
            k=(frozenset(ns['seq']),b,ns['inn'])
            if k not in nxt or nxt[k]['cost']>cost:nxt[k]=ns
            # close here: b is the last track and plays to its tail
            mb=_deck(ns['inn'],tr[b]['tail'],None,0);tot=bars+len(mb)-X;cb,lb_,_=K.close(b,mb,w['lv'],[],bars-X,tot)
            if LOB<=tot<=HIB and cb>=0.5 and lb_<=E4_BARS:done.append(dict(ns,cov=cv+[cb],bars=tot,bw=bw))
      S=sorted(nxt.values(),key=lambda s:s['cost'])[:beam]
  for d in done:
    n=len(d['bl']);d['pred']=dict(blends=n,bob16=sum(w['bob']>=16 for w in d['bl']),beatless=sum(w['beatless']>w['w'][4]/2 for w in d['bl']),
      x32=sum(w['w'][4]>=32 for w in d['bl']),cov_mean=round(float(np.mean(d['cov'])),3),cov_min=round(min(d['cov']),2),len_min=round(d['bars']*C.BAR/60,2))
    p=d['pred'];d['fails']=[k for k,ok in dict(bob16=p['bob16']>=n/2,beatless=p['beatless']<=n/3,x32=p['x32']>=n/2,coverage=p['cov_mean']>=0.8).items() if not ok]
  return done,K,round(time.time()-t0,1)
def to_plan(d,base):
  B={p['id']:p for p in json.load(open(base))};out=[]
  for i,b in enumerate(d['seq']):
    p=dict(B.get(b,{'id':b,'kw':{'pre':16,'build':True}}));p['tech']='first' if i==0 else 'blend'
    p.pop('out_win',None)
    if i<len(d['bl']):p['out_win']=d['bl'][i]['w']
    out.append(p)
  return out
def dry(plan,tag):
  """exact check: mix_simple --dry on the plan (no audio), then predict() on its meta"""
  import subprocess;f=f'_ps_{tag}.json';json.dump(plan,open(f,'w'))
  r=subprocess.run([sys.executable,'mix_simple.py','--plan',f,'--out',f'_ps_{tag}','--dry'],capture_output=True,text=True)
  try:
    if r.returncode:return dict(error=r.stderr.strip().splitlines()[-1] if r.stderr.strip() else 'mix_simple failed')
    return predict(f'_ps_{tag}_dry')
  finally:
    for x in(f,f'_ps_{tag}_dry_meta.json'):
      if os.path.exists(x):os.remove(x)
def report_missing(done,K):
  """what the crate lacks: tracks no window can bring in or take out, and how many pairs offer a 16+ bar beat-on-beat window"""
  T=K.T;tr=K.tr;ok=lambda w:not(w['voc'] or w['both']<8 or w['R']<0.2 or w['mel']>MELMAX)
  inn={b:sum(any(ok(w) for w in T['pairs'][f'{a}>{b}']['wins']) for a in tr if a!=b) for b in tr}
  out={a:sum(any(ok(w) for w in T['pairs'][f'{a}>{b}']['wins']) for b in tr if a!=b) for a in tr}
  bob={b:sum(any(ok(w) and w['bob']>=16 for w in T['pairs'][f'{a}>{b}']['wins']) for a in tr if a!=b) for b in tr}
  keys=sorted({t['key'] for t in tr.values()});allk=[f'{n}{l}' for l in 'AB' for n in range(1,13)]
  return dict(no_way_in=[b for b,n in inn.items() if n==0],no_way_out=[a for a,n in out.items() if n==0],
    bob16_pairs=sum(bob.values()),tracks_without_bob16_entry=[b for b,n in bob.items() if n==0],keys_missing=[k for k in allk if k not in keys])

# ---------- validation against renders ----------
def validate():
  """for every rendered mix: dry re-plan of its plan == its rendered meta? predicted E4 vs guardrail E4 (pre-E4 guardrail runs use the
  CLEANUP.md audit label), and the meta-only test targets"""
  late={'mixT':True}  # guard_mixT predates E4; CLEANUP.md 16:06 measured it failing E4 at 15:24
  rows=[]
  for g in sorted(glob.glob('guard_*/guardrails.json')):
    n=g.split('/')[0][6:];G=json.load(open(g))
    if not os.path.exists(f'{n}_meta.json'):continue
    e4=late.get(n,G['by_check'].get('E4',0)>0);p=predict(n)
    rows.append(dict(mix=n,E4_render=bool(e4),E4_pred=not p['tests']['E4'],guard_fails=G['n_fail'],pred=p['tests'],bob16=f"{p['bob16']}/{p['blends']}"))
  return rows
def same_as_render(name,plan,env_note=''):
  """re-run the render's plan dry and diff its deck maps + blends against the rendered meta"""
  import subprocess;R=json.load(open(f'{name}_meta.json'))
  r=subprocess.run([sys.executable,'mix_simple.py','--plan',plan,'--out','_ps_same','--dry'],capture_output=True,text=True)
  if r.returncode:return dict(error=r.stderr[-300:])
  D=json.load(open('_ps_same_dry_meta.json'));os.remove('_ps_same_dry_meta.json')
  dm=[a['full_map']==b['full_map'] and a['start_bar']==b['start_bar'] for a,b in zip(R['decks'],D['decks'])]
  tb=[(a['start_bar'],a['end_bar'])==(b['start_bar'],b['end_bar']) for a,b in zip(R['trans'],D['trans'])]
  return dict(decks_equal=f'{sum(dm)}/{len(dm)}',blends_equal=f'{sum(tb)}/{len(tb)}',len_render=round(R['len_sec']/60,2),len_dry=round(D['len_sec']/60,2))

if __name__=='__main__':
  a=sys.argv;cmd=a[1];arg=lambda k,d=None:a[a.index(k)+1] if k in a else d
  if cmd=='table':T=table(arg('--base'));print('tracks',len(T['tracks']),'key-ok pairs',sum(r['key_ok'] for r in T['pairs'].values()),'built_s',T['built_s'])
  elif cmd=='predict':print(json.dumps(predict(a[2]),indent=1))
  elif cmd=='validate':
    for r in validate():print(json.dumps(r))
  elif cmd=='search':
    base=arg('--base');t0=time.time();done,K,st=search(base,float(arg('--min',58)),float(arg('--max',62)),int(arg('--beam',300)),exclude=tuple(x for x in arg('--exclude','').split(',') if x))
    done.sort(key=lambda d:(len(d['fails']),d['pred']['bob16']<d['pred']['blends']/2+2,sum(w['pen'] for w in d['bl'])))  # all targets, then 2 blends of beat-on-beat margin, then the render scorer's own penalty
    print(f'search {st}s, {len(done)} complete plans, {sum(not d["fails"] for d in done)} meet every target on the table')
    best=None;tried=[];seen=set()  # dry-verify distinct orders (near-identical window variants share the same failure)
    for d in [d for d in done if not d['fails']]:
      if tuple(d['seq']) in seen:continue
      if len(seen)>=int(arg('--verify',25)):break
      seen.add(tuple(d['seq']));P=to_plan(d,base);v=dry(P,len(seen));tried.append((d['pred'],v.get('tests',v),v.get('E4')))
      if v.get('all_ok'):best=(P,d,v);break
    out=dict(runtime_s=round(time.time()-t0,1),search_s=st,complete=len(done),feasible_on_table=sum(not d['fails'] for d in done),verified=tried)
    if best:
      json.dump(best[0],open(arg('--out'),'w'),indent=1);out.update(plan=arg('--out'),pred=best[2],order=best[1]['seq'],blends=[dict(a=w['a'],b=w['b'],w=w['w'],bob=w['bob'],mel=w['mel'],rub=w['rub'],drift=w['drift']) for w in best[1]['bl']])
    else:
      fails={};[fails.__setitem__(f,fails.get(f,0)+1) for d in done[:200] for f in d['fails']]
      near=[d for d in done if len(d['fails'])==1];bob=max((d['pred']['bob16']/d['pred']['blends'] for d in done),default=0)
      dryf={};[dryf.__setitem__(k,dryf.get(k,0)+1) for _,t,_ in tried if isinstance(t,dict) for k,ok in t.items() if not ok]
      out.update(infeasible=True,binding=max(fails,key=fails.get) if fails else (f'every table-feasible order failed the dry run on: {dryf}' if tried else 'no complete plan (length/coverage/lull pruned everything)'),
        fail_counts_top200=fails,near_misses=[(d['fails'],d['pred']) for d in near[:3]],best_bob16_share=round(bob,3),crate=report_missing(done,K))
    print(json.dumps(out,indent=1,default=str))
