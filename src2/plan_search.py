"""Plan everything before rendering (additive to mix_simple.py; this file never renders audio).
  python3 plan_search.py table  --base plan.json           pairwise blend table for every analysed crate track -> pair_table.json (cached)
  python3 plan_search.py search --base plan.json --out p.json [--min 58 --max 62] [--exclude id,id] [--require a>b,...] [--open-any] [--ban a>b,...] (pairs a dry test proved bad)  (PREV_PLANS=a.json,b.json: cost for reused tracks/pairs)  (exclude = tracks a render proved unplaceable)   order + windows meeting every test target
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
DROPPEN=float(os.environ.get('DROPPEN',40));OUTPEN=float(os.environ.get('OUTPEN',20))  # structure targets (test_structure_tail): incoming drop at blend end, outgoing reaches its outro
BOTHMIN=int(os.environ.get('BOTHMIN',8))  # render c: O1 failed (5-7 heard bars) on windows the table scored at 8-10
ORDER=[x for x in os.environ.get('ORDER','').split(',') if x];PINW=json.loads(os.environ.get('PINW','{}'))  # fixed order / pinned windows {"a>b":[kind,e,p,ib,X]}
RELAXR=set(x for x in os.environ.get('RELAXR','').split(',') if x)  # pairs whose predicted-R filter is waived (the render's R1 guardrail still gates)
COVPEN=float(os.environ.get('COVPEN',50))  # per-blend cost for a closed deck playing under 85% of its loud bars
STEPMAX=float(os.environ.get('STEPMAX',9.5))  # predicted entry level step cap (guardrail N1): renders failed at +9.8/+10.2/+14.8; the one pass above it (+10.7) is Parallel->Bad To Me, which a render proved fine, so pairs the listener rated 4+ are exempt
STEPPEN=float(os.environ.get('STEPPEN',0))   # optional cost per dB of predicted entry step above 6 dB
PREFW=float(os.environ.get('PREFW',60))       # cost x techniques.pref_score (5 good=-60, 4 OK=0, <=3 bad=+60..+120); was centred on 3, which made 3/5 neutral (the listener 2026-10-31)
SIL_DB=20                                     # a source beat this far under the track's median is near-silent (guardrail E2 when it plays solo)
import techniques as TQ
LOVE={k for k in (json.load(open('track_prefs.json')) if os.path.exists('track_prefs.json') else {}) if not k.startswith('_')};LOVEW=float(os.environ.get('LOVEW',40))  # tracks the listener loves (goddard. - Lilies)
def prefs():return {k:v for k,v in json.load(open('pair_prefs.json')).items() if not k.startswith('_')}
BADC={}  # a>b -> [(window, guardrail code)] filled by bad_windows()
HARDCODES=set(os.environ.get('HARDCODES','A1').split(','))  # true hard rules: beats aligned (F1/G1), abrupt outgoing fade / silent-tail re-entry
def badw_cost(k,w):
  """render-proved failures of this exact window: hard only for HARDCODES, else BADWPEN per failure (the render guardrail re-checks)"""
  c=[code for ww,code in BADC.get(k,[]) if ww==w]
  if any(x in HARDCODES for x in c):return None
  return BADWPEN*len(c)
def bad_windows():
  """windows a render proved bad: every guardrail failure tied to a blend, from every guard_mixPlan*/ run, keyed a>b -> [window]"""
  out={}
  for g in glob.glob('guard_mixPlan*/guardrails.json')+glob.glob('guard_mix05*/guardrails.json')+glob.glob('guard_mix06[de]/guardrails.json')+glob.glob('guard_mix06i*/guardrails.json')+glob.glob('guard_mix05v2*/guardrails.json'):
    n=g.split('/')[0][6:];G=json.load(open(g))
    if not os.path.exists(f'{n}_meta.json'):continue
    M_=json.load(open(f'{n}_meta.json'));P={p['id']:p for p in M_['plan']}
    if int(os.environ.get('BADW_NEWONLY',0)) and not M_.get('eq_mode',{}).get('FADE'):continue  # pre-tail-fader renders: their L1/N1 bans don't carry over to the new engine (Mix 05 v2)
    for f in G['failures']:
      if f.get('trans') is None:f['trans']=f.get('trans_guess')  # mix-level checks (E1/E4/F1) tied to the nearest blend by the repair loop
      if f.get('trans') is None:continue
      t=G['transitions'][f['trans']] if isinstance(G['transitions'],list) else None
      a,b=(t['a'],t['b']) if t else (None,None);w=P.get(a,{}).get('out_win')
      if a and w:out.setdefault(f'{a}>{b}',[]).append(w);BADC.setdefault(f'{a}>{b}',[]).append((w,f.get('check')))
  SBF=os.environ.get('SEESAW_BANFILE')  # W1 see-saw windows the dry run predicted to fail (same ban as a render's W1 failure)
  if SBF and os.path.exists(SBF):
    for k,ws in json.load(open(SBF)).items():out.setdefault(k,[]).extend(ws)
  for r in ears_gate():  # ears + direct drum check both said off (src/tests/test_ears_gate.py)
    if r['status']=='confirmed' and r['out_win']:out.setdefault(f"{r['a']}>{r['b']}",[]).append(r['out_win'])
  return out
def ears_gate():return [r for g in sorted(glob.glob('*_ears_gate.json')) for r in json.load(open(g))]
SUSPPEN=float(os.environ.get('SUSPPEN',60))  # ears-suspect pair the listener rated 3 or less (Supernova->Solitude 3/5 'a little weird'): real but mild -> cost, not a ban
PREV=[f for f in os.environ.get('PREV_PLANS','').split(',') if f]  # delivered plans to stay fresh against (Mix 05: plan_60mL.json,plan_60pl6d.json); empty = old behaviour
FRESHPEN=float(os.environ.get('FRESHPEN',5));REUSEPEN=float(os.environ.get('REUSEPEN',30))  # cost per reused track / per repeated blend pair
def prev_used():
  T,P=set(),set()
  for f in PREV:
    q=[p['id'] for p in json.load(open(f))];T|=set(q);P|={f'{a}>{b}' for a,b in zip(q,q[1:])}
  return T,P
def suspects(PR):return {f"{r['a']}>{r['b']}" for r in ears_gate() if r['status']=='suspect' and PR.get(f"{r['a']}>{r['b']}",5)<=3}
SCORER_ENV=('XBARS','SWAP_POS','SWAP_PHRASE','HEAVY','BASS_SWAP_BARS','DRUMPEN','SGPEN','VPEN','BOTHPEN','GAPPEN','CUEW','LW','SEAMPEN','RPEN','HOLE_DB','HOLEPEN','SEAMMAX','BOTHMIN','HARDPEN','SHORTPEN','LOOPPEN','STRUCT','STRUCTW','LOOP32')
E4_DB,E4_BARS=10,12  # E4 on predicted (pre-master) levels: calibrated on 12 renders by `validate` (the master compresses dips, so 6 dB/8 bars in LUFS ~ 10 dB/12 bars here)
E4X={k:float(v) for k,v in (x.split(':') for x in os.environ.get('E4_RELAX','').split(',') if x)}  # per-track predicted-lull limit (bars); the render's E4 guardrail stays the judge
E4_REF_OFS=1.0  # whole-mix median sits ~0.7 dB above the median of the tracks' own medians (blends sum two decks); measured on a dry plan
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
  _reset(name);import test_mix02_traits as T2,test_mix as TM,test_structure_tail as TS,test_variety as TV;M=C.meta();D=M['decks']
  r=T2._drum_runs();n=len(r);K=C.keys()
  cov={d['id']:round(T2.body_coverage(d),2) for d in D if not d.get('acap')}
  def ok(f):
    try:f();return True
    except AssertionError:return False
    except Exception as ex:
      if type(ex).__name__=='Skipped':return False  # a skipped structure test means the meta is not a structure build: not a pass
      raise
  lens=[t['end_bar']-t['start_bar'] for t in M['trans'] if 'echo' not in t['tech']]
  keyclash=[(a['id'],b['id']) for a,b in zip(D,D[1:]) if not C.camelot_ok(K[a['id']],K[b['id']]) and C.harmonic_overlap(a,b)>2]
  e4=[(ts(i),j-i) for i,j in e4_runs(mix_levels(M))]
  p=dict(blends=n,bob16=sum(b>=16 for b,_,_ in r),beatless=sum(nn>x/2 for _,nn,x in r),x32=sum(x>=32 for x in lens),
    cov_mean=round(float(np.mean(list(cov.values()))),3),cov_min=min(cov.values()),cov_low=[k for k,v in cov.items() if v<0.5],
    drums_only_ok=ok(T2.test_no_long_drums_only_stretch),anchors_ok=ok(TM.test_anchor_tracks_long_enough),
    vocal_clash=[c for c in C.vocal_clashes() if not c['whitelisted'] and c['bars']>=1],key_clash=keyclash,E4=e4,
    len_min=round(max(d['end_bar'] for d in D)*C.BAR/60,2),drum_runs=[b for b,_,_ in r])
  p['tests']=dict(bob16=p['bob16']>=n/2,beatless=p['beatless']<=n/3,x32=p['x32']>=n/2,coverage=p['cov_mean']>=0.8 and p['cov_min']>=0.5,
    drums_only=p['drums_only_ok'],anchors=p['anchors_ok'],vocal=not p['vocal_clash'],keys=not keyclash,E4=not e4,
    structure=ok(TS.test_plan_respects_outro_and_intro),fader_tail=ok(TS.test_outgoing_fader_tail_is_gradual),lengths_vary=ok(TS.test_blend_lengths_vary),seesaw=not any(r['fails'] for r in __import__('seesaw').check(M)),variety=all(ok(getattr(TV,f)) for f in dir(TV) if f.startswith('test_') and f!='test_menu_lists_supported'))
  p['seesaw_fail']=[f"{r['a']}>{r['b']}" for r in __import__('seesaw').check(M) if r['fails']]
  p['all_ok']=all(p['tests'].values());return p

# ---------- pairwise blend table ----------
def scorer(base):
  """mix_simple's own window scorer (everything above its blend loop), loaded once: the table scores windows with the render's exact code"""
  src=open('mix_simple.py').read();sys.argv=['mix_simple.py','--plan',base,'--out','/dev/null']
  ns={'__name__':'mix_simple_scorer'};exec(compile(src[:src.index('LOOK=int(')],'mix_simple.py','exec'),ns);return ns
LX_PRE=int(os.environ.get('LX_PRE',8))  # = mix_simple: beat-only bars before an 'lx' blend
import beatstem;LXL=lambda b,p:beatstem.lx_len(b,p,float(os.environ.get('LOOP_DIP_DB',4)))
def windows(kind,e,p,ib,X,b_out=None):
  wa=[p+((LX_PRE+k)%LXL(b_out,p)) for k in range(X)] if kind=='lx' else [p+(k%16) for k in range(X)] if kind in('la','ab') else list(range(e-X,e))
  wb=[ib+(k%16) for k in range(X)] if kind in('lb','ab') else list(range(ib,ib+X));return wa,wb
def crate():
  K=C.keys();return sorted(b for b in (os.path.basename(f)[:-5] for f in glob.glob('st/*.json')) if b in K and glob.glob(f'st/{b}*.wav'))
def table_key(base):
  h=[os.environ.get(k) for k in SCORER_ENV]+[os.path.getmtime(f) for f in('mix_simple.py','cue_model.json','pair_feats.py','plan_search.py')]+[os.environ.get('TABLE_K','40')]
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
BOFFMAX=8  # = test_ears BEATOFF_MAX_BARS; the source-bar prediction matched the rendered ears count within 3 bars on all 37 blends of mixLen21b + mixPlan3
def beat_off_bars(pa,pb,da,db,wa,wb):
  """blend bars where both decks drum and their kick+snare patterns sit on different beats (ears.beat_off > 0.3, the test's threshold)"""
  import ears as E
  return sum(1 for sa,sb in zip(wa,wb) if sa<len(pa) and sb<len(pb) and sa<len(da) and sb<len(db) and da[sa] and db[sb] and E.beat_off(pa[sa],pb[sb])>0.3)
def entry_step(beats,wa,prev):
  """predicted master step at blend entry (guardrail N1): the outgoing deck's level over the first 3 beats of the window vs the last 3
  beats of the source bar it played just before (the incoming deck is still at gain 0)"""
  g=lambda s,q:beats[s*4+q] if 0<=s*4+q<len(beats) else -120.
  return round(float(np.median([g(wa[0],q) for q in range(3)])-np.median([g(prev,q) for q in (1,2,3)])),1)
def table(base,path=os.environ.get('PAIR_TABLE','pair_table.json'),K=int(os.environ.get('TABLE_K',40))):
  """every ordered pair of crate tracks: key compatibility, and for key-compatible pairs the K best windows (scored as if the outgoing
  track started at bar 0; search re-checks each window against the real start) with predicted beat-on-beat run, beatless bars, vocal clash
  bars, level dip, energy step, cue-model score and blend length. Cached; rebuilt when the scorer env, code, crate or anchors change."""
  key=table_key(base)
  if os.path.exists(path):
    T=json.load(open(path))
    if T['key']==key:return T
  import cue;CM=cue.load();ns=scorer(base);KE=C.keys();ids=crate();t0=time.time();tr={};pairs={};FT={b:PF.load(b) for b in ids};BT={b:PF.beats(b)[0] for b in ids};PT={b:PF.pattern(b) for b in ids}
  DA={b:(lambda x:x>np.percentile(x,75)-8)(np.array(json.load(open(f'st/{b}.json'))['bar']['drums'])) for b in ids}  # the ears test's drum-activity rule
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
          e,p=e if isinstance(e,tuple) else (e,None);wa,wb=windows(kind,e,p,ib,X,a)
          none=sum(not(xa<len(dA) and dA[xa]) and not(xb<len(dB) and dB[xb]) for xa,xb in zip(wa,wb))
          x=(np.arange(X)+.5)/X;lv=10*np.log10(np.cos(x*np.pi/2)**2*10**(alA[wa]/10)+np.sin(x*np.pi/2)**2*10**(alB[np.minimum(wb,len(alB)-1)]/10))
          row['wins'].append(dict(w=[kind,int(e),None if p is None else int(p),int(ib),int(X)],pen=round(float(r['pen']),1),bob=int(r['DT']),beatless=int(none),
            voc=int(r['V']),both=int(r['both']),L=int(r['L']),R=r['R'],dip=round(float(tr[a]['body']-lv.min()),1),lv=[round(float(x),1) for x in lv],cue=round(1-cue.pctl(CM,'out',tr[a]['cuef'],e),3),**clash(FT[a],FT[b],wa,wb),step=entry_step(BT[a],wa,e-1 if kind in('la','ab','lx') else wa[0]-1),boff=beat_off_bars(PT[a],PT[b],DA[a],DA[b],wa,wb)))
      pairs[f'{a}>{b}']=row
  for b in tr:tr[b].pop('cuef')
  T=dict(key=key,built_s=round(time.time()-t0,1),tracks=tr,pairs=pairs);json.dump(T,open(path,'w'));return T

# ---------- search over order + windows ----------
def _valid(t,w,ia):
  """can mix_simple pick window w for outgoing track t when t starts at bar ia (same limits as pair_cands)"""
  kind,e,p,ib,X=w;minlen=160 if t['anchor'] else 96-X;em=t['e_max']
  emin=max(ia+minlen,ia+int((em-ia)*0.5));emin+=(-emin)%16;emin=min(emin,em)
  if kind in('la','ab','lx') and X>16 and not int(os.environ.get('LOOP32',1)):return False  # 32-bar loop = outgoing phrase heard 3x (the 'echo' the listener hears)
  if kind in('la','ab','lx'):return e>=(max(ia+16,emin-X) if t['anchor'] else emin) and p>=max(ia,16)
  return e>=emin
def _deck(inn,e,p,Xout,kind_out=None,b_out=None):
  """source-bar map of a deck: incoming spec inn=(kind,ib,Xin), plays to e, then loops phrase p for Xout bars"""
  k,ib,Xin=inn;m=[ib+(j%16) for j in range(Xin)]+list(range(ib+16,e)) if k in('lb','ab') else list(range(ib,e))
  if kind_out=='lx':return m+[p+(j%LXL(b_out,p)) for j in range(Xout+LX_PRE)]
  return m+([p+(j%16) for j in range(Xout)] if p is not None else [])
class Crate:
  def __init__(s,T):
    s.T=T;s.tr=T['tracks'];s.al={b:C.src_bars(b) for b in s.tr};s.loud={b:set(np.where(a>np.percentile(a,75)-6)[0].tolist()) for b,a in s.al.items()}
    s.sil={}
    for b in s.tr:
      bt=PF.beats(b)[0];q=bt<np.median(bt)-SIL_DB;s.sil[b]={i//4 for i in range(1,len(q)) if q[i] and q[i-1]}  # source bars holding 2+ near-silent beats
    s.ref=float(np.median([np.median(a[:s.tr[b]['tail']]) for b,a in s.al.items()]))  # ~ the mix median level
  def close(s,b,m,lin,lout,at,end=1e9):
    """a finished deck starting at mix bar `at`, with the predicted mix levels of its incoming/outgoing blends:
    (coverage, longest run under the E4 line inside E4's window, seconds)"""
    cov=len(s.loud[b]&set(m))/max(1,len(s.loud[b]));al=s.al[b];run=best=0
    solo=m[len(lin):len(m)-len(lout)];hole=any(x in s.sil[b] for x in solo[2:])  # (the first bars of an opener / tail of the closer are E2-exempt via MIN_S anyway)
    if hole and MIN_S<=at+len(lin)<end-MIN_S:return cov,1e9,len(m)*C.BAR
    L=list(lin)+[al[x] if x<len(al) else -120 for x in m[len(lin):len(m)-len(lout)]]+list(lout)
    L=10*np.log10(np.maximum(np.convolve(10**(np.array(L,float)/10),np.ones(2)/2,'same'),1e-12))  # same 2-bar smoothing as e4_runs
    for j,l in enumerate(L):run=run+1 if MIN_S<=at+j<end-MIN_S and l<s.ref+E4_REF_OFS-E4_DB else 0;best=max(best,run)
    return cov,best,len(m)*C.BAR
import sections as SEC
def _drop_ok(w):
  """incoming's source bar at the blend end within 8 bars of its first drop (test_structure_tail)"""
  kind,e,p,ib,X=w['w'];at=ib+(16 if kind in('lb','ab') else X);return abs(at-SEC.get(w['b'])['drop1'])<=8
def _outro_ok(w):
  """outgoing leaves at or after its outro start"""
  return w['w'][1]>=SEC.get(w['a'])['outro_start']
def _rep_prefix_ok(bl):
  r=[w['w'][0] in('la','ab','lx') and w['w'][4]>16 for w in bl];NB=len(ORDER)-1 if ORDER else int(os.environ.get('NB_EXPECT',20))
  return sum(r)<=0.4*NB and not (len(r)>=3 and all(r[-3:]))
def _rep_ok(bl):
  """variety rule for the 32-bar outgoing repeat: <=40% of blends, never 3 in a row (test_variety)"""
  r=[w['w'][0] in('la','ab','lx') and w['w'][4]>16 for w in bl];return sum(r)<=0.4*len(r) and not any(all(r[i:i+3]) for i in range(len(r)-2))
FAMBAN=int(os.environ.get('FAMBAN',0))  # ban n/la/lb siblings of a render-failed window (same exit, entry, length: same overlap audio)
X16PEN=float(os.environ.get('X16PEN',30))
import collections
VOCPEN=float(os.environ.get('VOCPEN',25));BOTHSPEN=float(os.environ.get('BOTHSPEN',15));RSPEN=float(os.environ.get('RSPEN',400));MELSPEN=float(os.environ.get('MELSPEN',10));STEPSPEN=float(os.environ.get('STEPSPEN',20));BADWPEN=float(os.environ.get('BADWPEN',40));LXREPAIR=float(os.environ.get('LXREPAIR',60))
PREFWIN=json.loads(os.environ.get('PREFWIN','{}'));PREFPEN=float(os.environ.get('PREFPEN',60))  # the listener 2026-11-01: keep good Mix 05 choices as a strong soft preference
SOFT=int(os.environ.get('SOFT',0))  # 2026-11-01 17:15 ET listener: strict by default; options, not softness  # 2026-11-01 (listener: no hard 'never' rules): voc/both/R/mel/step/W1-type bans are search costs; the render guardrails C2/O1/R1/N1/W1 still verify
PROW=float(os.environ.get('PROW',0.15))
def _pro_template():
  p='/workspace/mixes/eval/control_curves_summary.json'
  if not os.path.exists(p):return None
  d=json.load(open(p))['median_curves_db_by_bar_rel_bass_swap'];W=dict(low=0.4,mid=0.4,high=0.2);bars=sorted({int(k) for b in d for k in d[b]['out']}&{int(k) for b in d for k in d[b]['in']})
  t={}
  for k in bars:
    tot=0
    for b,wt in W.items():
      o=d[b]['out'].get(str(k));i=d[b]['in'].get(str(k))
      if o is None or i is None:break
      tot+=wt*10*np.log10(10**(o[0]/10)+10**(i[0]/10))
    else:t[k]=tot
  return t
PROT=_pro_template()
_PSC={};_TOPW={};WIN_TOPK=int(os.environ.get('WIN_TOPK',60))
def pro_shape(w):
  k=id(w)
  if k not in _PSC:_PSC[k]=_pro_shape(w)
  return _PSC[k]
def _pro_shape(w):
  """0 (pro-like) .. 1: distance of the window's predicted summed level shape from the pros' median out+in curve, aligned on the blend middle (control_curves.md proposal; a tie-break, never a reject)"""
  if not PROT:return 0.0
  lv=w['lv'];X=len(lv);c=X//2;pairs=[(lv[j],PROT[j-c]) for j in range(X) if (j-c) in PROT]
  if len(pairs)<4:return 0.5
  a=np.array(pairs,float);a-=a.mean(0);return float(min(1.0,np.mean(np.abs(a[:,0]-a[:,1]))/6))
def soft_cost(k,w,PR):
  """search cost for what used to be a pre-reject"""
  c=VOCPEN*w['voc']+BOTHSPEN*max(0,BOTHMIN-w['both'])+(RSPEN*max(0,0.2-w['R']) if k not in RELAXR else 0)+MELSPEN*max(0,w['mel']-MELMAX)+(STEPSPEN*max(0,w['step']-STEPMAX) if PR.get(k,3)<4 else 0)
  if k in PREFWIN and w['w']!=PREFWIN[k]:c+=PREFPEN  # soft preference (Mix 05 blends / closed-loop strategy): a cost to deviate, never a lock
  return c
DBG=collections.Counter() if os.environ.get('PSDBG') else None
KILL=collections.Counter() if os.environ.get('PSKILL') else None
def search(base,lo=58,hi=62,beam=300,BW=(0,60,200),fix_open=True,exclude=(),ban=()):
  if len(crate())<2:raise SystemExit('crate empty: stems missing (cleaned?) - run python3 restore_audio.py first')
  T=table(base);K=Crate(T);PR=prefs();BADW=bad_windows();SUS=suspects(PR);PT,PP=prev_used();tr={b:t for b,t in K.tr.items() if b not in exclude};B=json.load(open(base));first=B[0]['id'] if fix_open else None;done=[];t0=time.time()
  LOB,HIB=lo*60/C.BAR,hi*60/C.BAR
  for bw in BW:
    starts=[first] if first else list(tr)
    S=[dict(seq=[b],inn=('n',0,0),lin=[],bl=[],cov=[],bars=0,cost=FRESHPEN*(b in PT)) for b in starts]
    while S:
      nxt={}
      for st in S:
        a=st['seq'][-1];ia=st['inn'][1]+16 if st['inn'][0] in('lb','ab') else st['inn'][1]
        for b in tr:
          if b in st['seq']:continue
          if ORDER and (len(st['seq'])>=len(ORDER) or b!=ORDER[len(st['seq'])]):continue  # Mix 05 v2: fixed track order
          row=T['pairs'][f'{a}>{b}']
          if not row['key_ok'] or f'{a}>{b}' in ban:continue
          if DBG is not None:DBG[(a[:4],b[:4],'wins',len(row['wins']),row['key_ok'])]+=1
          _ck=f'{a}>{b}'
          if _ck not in _TOPW:  # ranked shortlist per pair (score order, nothing filtered by rule): soft costs + pro_shape + render pen
            _TOPW[_ck]=sorted(row['wins'],key=lambda w:(soft_cost(_ck,w,PR) if SOFT else 0)+PROW*100*pro_shape(w)+w['pen']/100+X16PEN*(w['w'][4]<32))[:WIN_TOPK] if WIN_TOPK and _ck not in PINW else row['wins']
          for w in _TOPW[_ck]:
            if f'{a}>{b}' in PINW and w['w']!=PINW[f'{a}>{b}']:continue  # pinned window (the 5/5 gold blend)
            kind,e,p,ib,X=w['w']
            _k=f'{a}>{b}';_bc=badw_cost(_k,w['w']) if SOFT else (None if w['w'] in BADW.get(_k,[]) else 0)
            _why=('boff' if w['boff']>BOFFMAX else 'badw' if _bc is None else 'valid' if not _valid(tr[a],w['w'],ia) else None) if SOFT else ('voc' if w['voc'] else 'both' if w['both']<BOTHMIN else 'R' if (w['R']<0.2 and _k not in RELAXR) else 'mel' if w['mel']>MELMAX else 'boff' if w['boff']>BOFFMAX else 'badw' if _bc is None else 'step' if (w['step']>STEPMAX and PR.get(_k,3)<4) else 'valid' if not _valid(tr[a],w['w'],ia) else None)
            if KILL is not None:KILL[(a[:4]+'>'+b[:4],'seen')]+=1
            _pin=f'{a}>{b}' in PINW or PREFWIN.get(f'{a}>{b}')==w['w']  # pinned = already proven by a render (Mix 05 anchor / gold / closed-loop strategy): table filters don't apply
            if _pin:_why=None
            if _why:
              if KILL is not None:KILL[(a[:4]+'>'+b[:4],_why)]+=1
              continue
            m=_deck(st['inn'],e,p,X if p is not None else 0,kind,a)
            cov,lull,sec=K.close(a,m,st['lin'],w['lv'],st['bars']-st['inn'][2])
            if not _pin and (cov<0.5 or lull>E4X.get(a,E4_BARS) or (tr[a]['anchor'] and sec<C.MIN_ANCHOR_S)):
              if DBG is not None and w['w'][3]==80 and a.startswith('h1R'):DBG[(tuple(w['w']),st['inn'],round(cov,2),lull)]+=1
              if DBG is not None:DBG[(a,b,'cov' if cov<0.5 else ('lull',int(lull)) if lull>E4X.get(a,E4_BARS) else 'anchor')]+=1
              if KILL is not None:KILL[(a[:4]+'>'+b[:4],'cov' if cov<0.5 else 'lull' if lull>E4X.get(a,E4_BARS) else 'anchor')]+=1
              continue
            bars=st['bars']+len(m)-st['inn'][2]
            if bars>HIB:
              if DBG is not None:DBG[(a,b,'len')]+=1
              if KILL is not None:KILL[(a[:4]+'>'+b[:4],'len')]+=1
              continue
            bl=st['bl']+[dict(a=a,b=b,**w)];cv=st['cov']+[cov]
            if not _rep_prefix_ok(bl):
              if KILL is not None:KILL[(a[:4]+'>'+b[:4],'variety')]+=1
              continue
            if ORDER and not (PINW and len(PINW)>=len(ORDER)-1):  # bound: the remaining blends must still be able to reach every plan target
              NB=len(ORDER)-1;rem=NB-len(bl)  # 2026-11-01 19:30 ET: 32-bar/beat-on-beat counts are warnings (eval/calibration_notes.md), still costs (X16PEN/bw)
              if (os.environ.get('COUNTS_HARD')=='1' and (sum(x['bob']>=16 for x in bl)+rem<NB/2 or sum(x['w'][4]>=32 for x in bl)+rem<NB/2)) or sum(_outro_ok(x) for x in bl)+rem<0.7*NB or sum(_drop_ok(x) for x in bl)+rem<NB*float(os.environ.get('DROP_FRAC',1/3)):
                if KILL is not None:KILL[(a[:4]+'>'+b[:4],'target_bound')]+=1
                continue
            if KILL is not None:KILL[(a[:4]+'>'+b[:4],'survive')]+=1
            _soft=(soft_cost(_k,w,PR)+_bc-(LXREPAIR if kind=='lx' and _k in BADC else 0)) if SOFT else 0
            cost=st['cost']+_soft+PROW*100*pro_shape(w)+w['pen']/100+bw*(w['bob']<16)+X16PEN*(X<32)+60*(w['beatless']>X/2)+COVPEN*max(0,0.85-cov)+MELPEN*w['mel']*w['rub']/0.25+DRIFTPEN*max(0,w['drift']-5)+STEPPEN*max(0,w['step']-6)-PREFW*(TQ.pref_score(PR[f'{a}>{b}']) if f'{a}>{b}' in PR else 0)+SUSPPEN*(f'{a}>{b}' in SUS)+FRESHPEN*(b in PT and b not in LOVE)-LOVEW*(b in LOVE)+REUSEPEN*(f'{a}>{b}' in PP)+DROPPEN*(not _drop_ok(dict(a=a,b=b,**w)))+OUTPEN*(not _outro_ok(dict(a=a,b=b,**w)))
            ns=dict(seq=st['seq']+[b],inn=(kind,ib,X),lin=w['lv'],bl=bl,cov=cv,bars=bars,cost=cost)
            k=(frozenset(ns['seq']),b,ns['inn'])+((sum(x['bob']>=16 for x in bl),sum(x['w'][4]>=32 for x in bl),sum(_drop_ok(x) for x in bl),sum(_outro_ok(x) for x in bl)) if ORDER else ())  # fixed order: keep states that differ in plan-target counts
            if k not in nxt or nxt[k]['cost']>cost:nxt[k]=ns
            # close here: b is the last track and plays to its tail
            mb=_deck(ns['inn'],tr[b]['tail'],None,0);tot=bars+len(mb)-X;cb,lb_,_=K.close(b,mb,w['lv'],[],bars-X,tot)
            # all-pinned chain may be short: only a seed for autoloop's length fill (PS_KEEP), which enforces the 56-min floor with longer passing candidates
            _fp=bool(ORDER and PINW and len(PINW)>=len(ORDER)-1)
            if _fp and len(ns['seq'])==len(ORDER):print(f'pinned chain complete: {tot} bars (target {LOB}-{HIB}), last cov {cb:.2f}, lull {lb_}',flush=True)
            if (not ORDER or len(ns['seq'])==len(ORDER)) and ((LOB<=tot<=HIB and cb>=0.5 and lb_<=E4_BARS) or (_fp and os.environ.get('PS_KEEP') and len(ns['seq'])==len(ORDER))):done.append(dict(ns,cov=cv+[cb],bars=tot,bw=bw))
      S=sorted(nxt.values(),key=lambda s:s['cost'])[:beam]
      print('depth',len(S[0]['seq']) if S else 0,'states',len(S),'done',len(done),round(time.time()-t0),'s',flush=True)
      if KILL is not None:print('PSKILL bw',bw,'depth',len(S[0]['seq']) if S else 0,'states',len(S),json.dumps({f'{k[0]} {k[1]}':v for k,v in sorted(KILL.items())}),flush=True);KILL.clear()
      if os.environ.get('PSDBG'):print('PSDBG bw',bw,'depth',len(S[0]['seq']) if S else None,'states',len(S),'done',len(done),dict(DBG),flush=True);DBG.clear()
  for d in done:
    n=len(d['bl']);d['pred']=dict(blends=n,bob16=sum(w['bob']>=16 for w in d['bl']),beatless=sum(w['beatless']>w['w'][4]/2 for w in d['bl']),
      x32=sum(w['w'][4]>=32 for w in d['bl']),cov_mean=round(float(np.mean(d['cov'])),3),cov_min=round(min(d['cov']),2),len_min=round(d['bars']*C.BAR/60,2))
    p=d['pred'];p['drop_end']=sum(_drop_ok(w) for w in d['bl']);p['outro']=sum(_outro_ok(w) for w in d['bl'])
    d['fails']=[k for k,ok in dict(bob16=p['bob16']>=n/2,beatless=p['beatless']<=n/3,x32=p['x32']>=n/2,coverage=p['cov_mean']>=0.8,
      drop_end=p['drop_end']>=n*float(os.environ.get('DROP_FRAC',1/3)),repeat_share=_rep_ok(d['bl']),outro=p['outro']>=0.7*n).items() if not ok]  # the last two = test_structure_tail's plan targets
  return done,K,round(time.time()-t0,1)
def nudge_kind(w0,w1):
  """which ladder rung turns the pair's natural first choice w0 into the chosen w1"""
  if w0==w1:return 'none'
  k0,e0,p0,i0,X0=w0;k1,e1,p1,i1,X1=w1
  if k1=='lx' and k0!='lx':return 'beat_outro_lx'
  if k1 in('la','ab','lx') and k0 in('la','ab','lx') and (X1<X0 or p1!=p0):return 'shorter_cleaner_loop'
  if e1>e0:return 'longer_outgoing_ride'
  if X1!=X0:return 'blend_length'
  return 'cue_phrase'
def nudge_log(d,out):
  """per pair: natural first choice (lowest render-scorer pen, ignoring every soft cost) vs chosen window -> mix05v2/nudges.jsonl (what fixed each stuck pair)"""
  T=table(os.environ.get('NUDGE_BASE','plan_mix05v2_base.json'));L=os.environ.get('NUDGE_LOG','/workspace/mixes/mix05v2/nudges.jsonl')
  with open(L,'a') as f:
    for w in d['bl']:
      k=f"{w['a']}>{w['b']}";W=T['pairs'][k]['wins'];w0=min(W,key=lambda x:x['pen'])
      stuck=bool(w0['voc'] or w0['both']<BOTHMIN or w0['R']<0.2 or w0['mel']>MELMAX or w0['step']>STEPMAX or badw_cost(k,w0['w']))
      f.write(json.dumps(dict(t=time.strftime('%H:%M'),plan=out,pair=k,first=w0['w'],chosen=w['w'],stuck=stuck,nudge=nudge_kind(w0['w'],w['w']),soft=round(soft_cost(k,w,{}),1),pro_shape=round(pro_shape(w),2)))+'\n')
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
    for x in(() if os.environ.get('PS_KEEP') else (f,))+(f'_ps_{tag}_dry_meta.json',):
      if os.path.exists(x):os.remove(x)
def report_missing(done,K):
  """what the crate lacks: tracks no window can bring in or take out, and how many pairs offer a 16+ bar beat-on-beat window"""
  T=K.T;tr=K.tr;ok=lambda w:not(w['voc'] or w['both']<8 or w['R']<0.2 or w['mel']>MELMAX or w['boff']>BOFFMAX)
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
    base=arg('--base');t0=time.time();done,K,st=search(base,float(arg('--min',58)),float(arg('--max',62)),int(arg('--beam',300)),BW=tuple(float(x) for x in os.environ.get('BW','0,60,200').split(',')),exclude=tuple(x for x in arg('--exclude','').split(',') if x),fix_open='--open-any' not in a,ban=tuple(x for x in arg('--ban','').split(',') if x))
    done.sort(key=lambda d:(len(d['fails']),d['pred']['bob16']<d['pred']['blends']/2+2,sum(w['pen'] for w in d['bl'])+PROW*100*sum(pro_shape(w) for w in d['bl'])))  # all targets, then 2 blends of beat-on-beat margin, then the render scorer's own penalty
    print(f'search {st}s, {len(done)} complete plans, {sum(not d["fails"] for d in done)} meet every target on the table')
    best=None;w1best=None;tried=[];seen=set()  # dry-verify distinct orders (near-identical window variants share the same failure)
    req=[x for x in arg('--require','').split(',') if x]  # pairs that must appear, e.g. a 5/5-rated blend: 2s3M6oX2lfo>nT25guf4DRU
    # 2026-11-01 14:05: dry runs are ~37 s each and ran one at a time with no output, so --verify 100 took ~60 min, past autoloop's 40 min
    # search timeout (looked hung). Now NPAR (4) dry runs in parallel, a progress line per run, and a DRY_BUDGET_S wall cap (default 1200 s).
    from concurrent.futures import ThreadPoolExecutor
    NPAR=int(os.environ.get('NPAR',4));BUD=float(os.environ.get('DRY_BUDGET_S',1200));tv=time.time()
    _FP=bool(ORDER and PINW and len(PINW)>=len(ORDER)-1)
    pool=[d for d in done if (_FP or not d['fails']) and all(r in {f"{w['a']}>{w['b']}" for w in d['bl']} for r in req)];pi=0
    print(f'dry-verify: {len(pool)} candidate plans, up to {arg("--verify",25)} distinct, {NPAR} parallel, budget {BUD:.0f}s',flush=True)
    while not best and pi<len(pool) and len(seen)<int(arg('--verify',25)) and time.time()-tv<BUD:
      _sbf=os.environ.get('SEESAW_BANFILE');_SB=json.load(open(_sbf)) if _sbf and os.path.exists(_sbf) else {}
      batch=[]
      while pi<len(pool) and len(batch)<NPAR and len(seen)<int(arg('--verify',25)):
        d=pool[pi];pi+=1
        vk=tuple(tuple(w['w']) for w in d['bl']) if ORDER else tuple(d['seq'])  # fixed ORDER: dedupe on windows
        if vk in seen or any(w['w'] in _SB.get(f"{w['a']}>{w['b']}",[]) for w in d['bl']):continue
        seen.add(vk);batch.append((d,to_plan(d,base),len(seen)))
      if not batch:break
      with ThreadPoolExecutor(len(batch)) as ex:res=list(ex.map(lambda x:dry(x[1],x[2]),batch))
      for (d,P,k),v in zip(batch,res):
        tried.append((d['pred'],v.get('tests',v),v.get('E4')))
        print(f"dry {k}: {'ALL OK' if v.get('all_ok') else 'fail '+str([t for t,o in (v.get('tests') or {}).items() if not o] or v.get('error'))} ({time.time()-tv:.0f}s)",flush=True)
        SBF=os.environ.get('SEESAW_BANFILE')
        if SBF and v.get('seesaw_fail'):
          SB=json.load(open(SBF)) if os.path.exists(SBF) else {};W={f"{w['a']}>{w['b']}":w['w'] for w in d['bl']}
          for kk in v['seesaw_fail']:
            if kk in W and W[kk] not in SB.setdefault(kk,[]):SB[kk].append(W[kk])
          json.dump(SB,open(SBF,'w'))
        if v.get('all_ok') and not best:best=(P,d,v)
        if SOFT and isinstance(v.get('tests'),dict) and all(ok for t,ok in v['tests'].items() if t!='seesaw'):
          if not w1best or len(v.get('seesaw_fail',[]))<len(w1best[2].get('seesaw_fail',[])):w1best=(P,d,v)
    # 2026-11-01 17:15 ET listener: no silent fallback plan; 'no plan' -> caller escalates (ESCALATE.json + A/B)
    out=dict(runtime_s=round(time.time()-t0,1),search_s=st,complete=len(done),feasible_on_table=sum(not d['fails'] for d in done),verified=tried)
    if best:
      json.dump(best[0],open(arg('--out'),'w'),indent=1);nudge_log(best[1],arg('--out'))
      out.update(plan=arg('--out'),pred=best[2],order=best[1]['seq'],blends=[dict(a=w['a'],b=w['b'],w=w['w'],bob=w['bob'],mel=w['mel'],rub=w['rub'],drift=w['drift']) for w in best[1]['bl']])
    else:
      fails={};[fails.__setitem__(f,fails.get(f,0)+1) for d in done[:200] for f in d['fails']]
      near=[d for d in done if len(d['fails'])==1];bob=max((d['pred']['bob16']/d['pred']['blends'] for d in done),default=0)
      dryf={};[dryf.__setitem__(k,dryf.get(k,0)+1) for _,t,_ in tried if isinstance(t,dict) for k,ok in t.items() if not ok]
      out.update(infeasible=True,binding=max(fails,key=fails.get) if fails else (f'every table-feasible order failed the dry run on: {dryf}' if tried else 'no complete plan (length/coverage/lull pruned everything)'),
        fail_counts_top200=fails,near_misses=[(d['fails'],d['pred']) for d in near[:3]],best_bob16_share=round(bob,3),crate=report_missing(done,K))
    print(json.dumps(out,indent=1,default=str))
