"""DJustify-style plan repair: when a blend fails a gate, swap the INCOMING track instead of re-tweaking the same pair.
  python3 repair.py --plan plan.json --out fixed.json [--render NAME] [--culprit a>b[:code],...] [--budget-s 1800] [--max-dry 150]
Culprits (failing pairs) come from a render's guardrails.json + pytest output (--render NAME) and/or the dry check of the plan itself.
For each culprit a>b the repair tries, cheapest first: replace b with an unused crate track c (a>c and c>next both key-compatible
with a legal window), or insert c between a and b. Windows for every new pair are re-picked from the pair table with the planner's
own SOFT=0 filters (no vocal overlap, ib<=80, _valid, drums-solo rule, render-proved bad windows banned). Each candidate is checked
with plan_search.dry(); the first that is all_ok and >= MIN_LEN minutes is kept, then the next culprit is repaired on top of it.
Nothing here loosens a test: dry() runs the release tests' own functions, and the render still runs every guardrail and pytest."""
import os,re,sys,json,time,itertools
LOOPS=('la','ab','lx','lb')
PHASE_CODES={'G1','F1','downbeats','beat_aligned'}   # beat-phase failures: a looped outgoing deck is the usual cause (r9c 37:31)
TAIL_CODES={'tail','A1'}                              # abrupt outgoing tail: avoid the same exit bar
IBMAX=int(os.environ.get('IBMAX',80))
NO_LX=int(os.environ.get('REPAIR_NO_LX',1))  # Mix 08: beat-stem loop exits slipped +8 ms (G1) on two different tracks (r9c Stars, r10x Shadows): re-picks never use lx
LXPEN=float(os.environ.get('REPAIR_LXPEN',30))  # Mix 08 r9c: a beat-stem loop (lx) exit slipped +8 ms (G1); re-picked windows prefer plain/la exits
SOFTPEN=float(os.environ.get('SOFTPEN',30))  # soft-tier windows rank after every strict one
ALTS=int(os.environ.get('REPAIR_ALTS',3));REWINDOW_ALTS=int(os.environ.get('REWINDOW_ALTS',16))
PAIR_TESTS={'vocal','keys','seesaw'};PAD_MAX=float(os.environ.get('PAD_MAX',4));PAD_K=int(os.environ.get('PAD_K',20));DEPTH2_K=int(os.environ.get('DEPTH2_K',6))
MIN_LEN=float(os.environ.get('MIN_LEN',60))
TEST_CODES={'test_no_bass_gap_in_overlaps':'bassgap','test_no_level_dip_at_swap':'swapdip','test_downbeats_aligned':'downbeats',
  'test_mixdown_beats_aligned_every_overlap_bar':'beat_aligned','test_outgoing_audio_tail_never_drops_abruptly':'tail'}
FILE_CODES={'structure_tail':'tail','bassgap':'bassgap','eq_swap':'swapdip','mix':'downbeats'}
PAIRRE=re.compile(r"'([A-Za-z0-9_-]{11})',\s*'([A-Za-z0-9_-]{11})'")
YT=re.compile(r"'([A-Za-z0-9_-]{11})'")
MMSS=re.compile(r'\b(\d{1,2}):(\d{2})\b')

# ---------- culprits ----------
def _trans_at(M,sec,pre_bars=16):
  """index of the blend whose window (plus a loop pre-roll of pre_bars before it) holds sec; nearest blend start otherwise"""
  bs=M['bar_sec'];T=M['trans']
  for i,t in enumerate(T):
    if (t['start_bar']-pre_bars)*bs<=sec<=t['end_bar']*bs:return i
  return min(range(len(T)),key=lambda i:abs(T[i]['start_bar']*bs-sec)) if T else None
def render_culprits(name,log=None,src='.'):
  """[(a,b,code)] for every render failure tied to a blend: guardrails.json (trans index or time) and pytest assertion text
  (outgoing id + start bar, or mm:ss). Mix-level fails with no locatable blend are skipped (they are not a pair's fault)."""
  out=[];mp=os.path.join(src,f'{name}_meta.json')
  if not os.path.exists(mp):return out
  M=json.load(open(mp));T=M['trans']
  def add(i,code):
    if i is not None and 0<=i<len(T):out.append((T[i]['a'],T[i]['b'],code))
  g=os.path.join(src,f'guard_{name}','guardrails.json')
  if os.path.exists(g):
    for f in json.load(open(g)).get('failures',[]):
      add(f['trans'] if f.get('trans') is not None else _trans_at(M,f['sec']) if f.get('sec') is not None else None,f.get('check'))
  for lp in [x for x in (log,os.path.join(src,f'guard_{name}','pytest.log')) if x and os.path.exists(x)]:
    txt=open(lp,errors='replace').read();cur='pytest';pend=[]  # a tailed log may have lost the test header; the "file.py:N: AssertionError" line follows the E lines
    for line in txt.splitlines():
      m=re.match(r'_+ (test_\w+) _+',line.strip())
      if m:
        for i in pend:add(i,cur)
        pend=[];cur=TEST_CODES.get(m.group(1),m.group(1));continue
      m=re.search(r'test_release_(\w+)\.py:\d+: AssertionError',line)
      if m:
        code=FILE_CODES.get(m.group(1),m.group(1)) if cur=='pytest' else cur
        for i in pend:add(i,code)
        pend=[];continue
      if not line.lstrip().startswith('E ') or 'assert not' in line:continue
      if 'bass gaps (trans' in line:  # test_release_bassgap: (trans index, mix bar, bars)
        pend+=[int(x) for x in re.findall(r'\((\d+),\s*\d+,\s*\d+\)',line)];continue
      pairs=PAIRRE.findall(line)
      if pairs:  # ('a', 'b', ...) tuples name the blend directly (test_release_eq_swap)
        for a,b in pairs:pend+=[i for i,t in enumerate(T) if t['a']==a and t['b']==b][:1]
        continue
      ids=YT.findall(line);bars=[int(x) for x in re.findall(r"'[A-Za-z0-9_-]{11}',\s*(\d+)",line)]
      for k,a in enumerate(ids):
        c=[i for i,t in enumerate(T) if t['a']==a and (k>=len(bars) or t['start_bar']==bars[k])] or [i for i,t in enumerate(T) if t['a']==a]
        if c:pend.append(c[0])
      if not ids:
        for mm,ss in MMSS.findall(line):pend.append(_trans_at(M,int(mm)*60+int(ss)))
    for i in pend:add(i,cur)
  seen=set();res=[]
  for a,b,c in out:
    if (a,b,c) not in seen:seen.add((a,b,c));res.append((a,b,c))
  return res
def render_bad_windows(name,log=None,src='.'):
  """{(a,b,window)} every blend a render failed, with the exact window that render used (from its meta plan): a repair
  may keep the pair but never that window again"""
  mp=os.path.join(src,f'{name}_meta.json')
  if not os.path.exists(mp):return set()
  W={p['id']:p.get('out_win') for p in json.load(open(mp))['plan']}
  return {(a,b,tuple(W[a])) for a,b,_ in render_culprits(name,log,src) if W.get(a)}
def dry_culprits(p):
  """[(a,b,code)] for dry failures that name a pair (vocal clash, key clash, see-saw)"""
  r=[(c['a'],c['b'],'vocal') for c in p.get('vocal_clash',[])]+[(a,b,'keys') for a,b in p.get('key_clash',[])]
  r+=[tuple(k.split('>'))+('seesaw',) for k in p.get('seesaw_fail',[])];return r
def passes(p):return bool(p) and not p.get('error') and p.get('all_ok') and p.get('len_min',0)>=MIN_LEN

# ---------- window choice (planner's SOFT=0 rules) ----------
class Ctx:
  """table + rule callables; the default binds plan_search (fresh rows from each outgoing's real entry bar), tests inject synthetic ones"""
  def __init__(s,T,crate,ok=None,cost=None,dry=None,row=None,base=None,soft=None):
    s.badwin=set();s.T=T;s.crate=list(crate);s.ok=ok or _ps_ok();s.cost=cost or _ps_cost();s.dry=dry;s._rows={}
    s.soft=soft if soft is not None else (None if ok else _ps_soft())  # second tier: only hard rules filter, table predictions become costs
    s.row=row or (_ps_row(base) if base else (lambda a,b,ia:T['pairs'].get(f'{a}>{b}')))
def _ps_row(base):
  import plan_search as PS;KE=PS.C.keys();cache={}
  def row(a,b,ia):
    if not PS.C.camelot_ok(KE[a],KE[b]):return None
    k=(a,b,ia)
    if k not in cache:cache[k]=PS.pair_rows(base,[(a,b)],K=400,ia={a:ia})[f'{a}>{b}']
    return cache[k]
  return row
def _ps_ok():
  import plan_search as PS
  BADW=PS.bad_windows();PR=PS.prefs()
  def ok(T,a,b,w,ia):
    k=f'{a}>{b}';kind,e,p,ib,X=w['w']
    if w['voc'] or w['both']<PS.BOTHMIN or (w['R']<0.2 and k not in PS.RELAXR) or w['mel']>PS.MELMAX or w['boff']>PS.BOFFMAX:return False
    if w['step']>PS.STEPMAX and PR.get(k,3)<4:return False
    if w['w'] in BADW.get(k,[]) or ib>IBMAX:return False
    if not PS._valid(T['tracks'][a],w['w'],ia):return False
    return PS._drums_solo_ok(dict(a=a,b=b,**w))
  return ok
def _ps_soft():
  """(ok, extra cost) when the strict SOFT=0 filter leaves nothing: keep the hard rules (ib<=80, _valid, render-proved bad windows,
  drums-only solo) and charge the planner's own soft_cost for voc/both/R/mel/step. The dry check (the release tests' functions) then
  decides; no test threshold moves."""
  import plan_search as PS
  BADW=PS.bad_windows();PR=PS.prefs()
  def soft(T,a,b,w,ia):
    k=f'{a}>{b}';ib=w['w'][3]
    if w['w'] in BADW.get(k,[]) or ib>IBMAX or w['boff']>PS.BOFFMAX:return None
    if not PS._valid(T['tracks'][a],w['w'],ia) or not PS._drums_solo_ok(dict(a=a,b=b,**w)):return None
    return PS.soft_cost(k,w,PR)
  return soft
def _ps_cost():
  import plan_search as PS
  def cost(T,a,b,w):
    d=dict(a=a,b=b,**w)
    return PS.PROW*100*PS.pro_shape(w)+w['pen']/100+PS.X16PEN*(w['w'][4]<32)+PS.DROPPEN*(not PS._drop_ok(d))+PS.OUTPEN*(not PS._outro_ok(d))
  return cost
def _airtime(w):
  """rough bars a window adds to the mix: later exit, earlier incoming entry, outgoing loop bars; overlap counted once"""
  k,e,p,ib,X=w;return e-ib-X+(X if k in('la','ab','lx') else 0)+(16 if k in('lb','ab') else 0)
def _ia(w):return 0 if w is None else (w[3]+16 if w[0] in('lb','ab') else w[3])
def ia_of(plan,i):
  """source bar track i enters at = the previous blend's incoming bar (+16 for an incoming loop)"""
  return 0 if i==0 else _ia(plan[i-1]['out_win'])
def pick(ctx,a,b,ia,avoid=(),k=4,fill=False):
  """k cheapest legal windows for a>b, given a enters at bar ia; avoid = callables w->True to skip (culprit-specific)"""
  row=ctx.row(a,b,ia)
  if not row or not row.get('key_ok'):return []
  ws=[w for w in row['wins'] if not any(f(w['w']) for f in avoid) and (a,b,tuple(w['w'])) not in ctx.badwin and not (NO_LX and w['w'][0]=='lx')]
  strict=[(ctx.cost(ctx.T,a,b,w)+LXPEN*(w['w'][0]=='lx'),w['w']) for w in ws if ctx.ok(ctx.T,a,b,w,ia)]
  strict=sorted(strict,key=lambda x:x[0])
  if not ctx.soft or (strict and (not fill or len(strict)>=k)):return strict[:k]
  soft=[(ctx.cost(ctx.T,a,b,w)+LXPEN*(w['w'][0]=='lx')+SOFTPEN+c,w['w']) for w in ws for c in [ctx.soft(ctx.T,a,b,w,ia)] if c is not None]
  return (strict+sorted([x for x in soft if x[1] not in [w for _,w in strict]],key=lambda x:x[0]))[:k]  # fill: soft ones after every strict one
def _avoid(old_w,codes):
  f=[]
  if old_w and set(codes)&PHASE_CODES and old_w[0] in LOOPS:f.append(lambda w,k=old_w[0]:w[0] in(k,'lx'))  # the looped kind that slipped, and the beat-stem loop; plain or la still allowed
  if old_w and set(codes)&TAIL_CODES:f.append(lambda w,e=old_w[1]:w[1]==e)
  return f
def _step(pid,w,base=None):
  d=dict(base or {'id':pid,'kw':{'pre':16,'build':True},'anchor':False});d['id']=pid;d['tech']='blend'
  if w is None:d.pop('out_win',None)
  else:d['out_win']=list(w)
  return d
MOVEPEN=dict(drop_out=20,rewindow=10,replace_in=0,insert=5,swap_in=15,move_in=15,drop_in=20,replace_out=25,swap_out=35)
def seq_moves(ids,i,unused):
  """(move, track, new order) re-picking the slot after blend i first (DJustify: the incoming track), then the outgoing slot.
  Unused crate tracks first; tracks already in the plan can be moved into the slot (their old neighbours re-join)."""
  a,b=ids[i],ids[i+1];n=len(ids)
  for c in unused:yield 'replace_in',c,ids[:i+1]+[c]+ids[i+2:]
  for c in unused:yield 'insert',c,ids[:i+1]+[c]+ids[i+1:]
  for j,d in enumerate(ids):
    if j in(i,i+1):continue
    s=list(ids);s[i+1],s[j]=s[j],s[i+1];yield 'swap_in',d,s
    s=[x for x in ids if x!=d];s.insert(s.index(a)+1,d);yield 'move_in',d,s
  yield 'drop_in',b,ids[:i+1]+ids[i+2:]
  if i>0:
    yield 'drop_out',a,ids[:i]+ids[i+1:]
    for c in unused:yield 'replace_out',c,ids[:i]+[c]+ids[i+1:]
    for j,d in enumerate(ids):
      if j in(0,i,i+1):continue
      s=list(ids);s[i],s[j]=s[j],s[i];yield 'swap_out',d,s
def build(ctx,plan,seq,avoid,ban=(),alt=0,force=None,fill=False):
  """plan for order seq: keep every old window whose pair and entry bar are unchanged (and still legal), re-pick the rest
  (cheapest legal; the first new pair of the culprit outgoing honours avoid). Returns (cost, plan) or None."""
  old={p['id']:p for p in plan};oldnext={plan[k]['id']:plan[k+1]['id'] for k in range(len(plan)-1)};oldia={p['id']:ia_of(plan,k) for k,p in enumerate(plan)}
  P=[];ia=0;cost=0.0
  for k,t in enumerate(seq):
    if k==len(seq)-1:P.append(_step(t,None,old.get(t)));break
    nx=seq[k+1]
    if (t,nx) in ban and oldnext.get(t)!=nx:return None  # never create a failed pair; ones still waiting their own turn may stay
    w=None
    if t!=force and oldnext.get(t)==nx and oldia.get(t)==ia and old[t].get('out_win'):w=list(old[t]['out_win'])
    if w is None:
      c=pick(ctx,t,nx,ia,avoid.get(t,()),alt+1,fill and t==force)
      if len(c)<=alt:return None
      cost+=c[alt][0];w=c[alt][1];alt=0  # alt = the first re-picked pair's 2nd/3rd best window; later pairs take their best
    P.append(_step(t,w,old.get(t)));ia=_ia(w)
  if plan and P:P[0]['tech']='first'
  return cost,P
def candidates(ctx,plan,i,codes,ban=()):
  ids=[p['id'] for p in plan];used=set(ids);unused=[c for c in ctx.crate if c not in used];a=ids[i]
  avoid={a:_avoid(plan[i].get('out_win'),codes)};out=[];seen=set()
  for move,c,seq in seq_moves(ids,i,unused):
    if tuple(seq) in seen:continue
    if (ids[i],ids[i+1]) in list(zip(seq,seq[1:])):continue  # the culprit blend itself must go
    seen.add(tuple(seq))
    for alt in range(ALTS):
      r=build(ctx,plan,seq,avoid,ban,alt)
      if r:out.append((r[0]+MOVEPEN[move],move,c,r[1]))
  if set(codes)&(PHASE_CODES|TAIL_CODES) and avoid[a]:
    # same tracks, clearly different window: a phase slip on a loop gets a non-loop/la exit, an abrupt tail a different exit bar
    for alt in range(REWINDOW_ALTS):  # every legal exit of the same pair (a plain or la exit replacing a slipped beat-stem loop), cheapest first
      r=build(ctx,plan,ids,avoid,set(ban)-{(ids[i],ids[i+1])},alt,force=a,fill=True)
      if r:out.append((r[0]+MOVEPEN['rewindow'],'rewindow',ids[i+1],r[1]))
  out.sort(key=lambda x:x[0]);return out

# ---------- the loop ----------
def repair(plan,culprits,ctx,budget_s=1800,max_dry=150,log=print,tag='repair',ban=()):
  """returns (plan, result, history). Every culprit pair is banned from the new plan (it failed a gate: render or dry),
  so a pass means each one got a different incoming (or outgoing) track. history: one dict per culprit."""
  t0=time.time();n=[0];hist=[];tried=set();ban=set(ban)|{(a,b) for a,b,_ in culprits}
  def dry(P):
    n[0]+=1;return ctx.dry(P,f'{tag}{n[0]}')
  cur=[dict(x) for x in plan];res=dry(cur)
  if not passes(res):culprits=list(culprits)+dry_culprits(res);ban|={(a,b) for a,b,_ in culprits}
  by={}
  for a,b,c in culprits:by.setdefault((a,b),[]).append(c)
  todo=[(k,v,0) for k,v in by.items()]
  while todo:
    (a,b),codes,pas=todo.pop(0);ids=[p['id'] for p in cur]
    i=next((k for k in range(len(ids)-1) if ids[k]==a and ids[k+1]==b),None)
    if i is None:hist.append(dict(pair=f'{a}>{b}',codes=codes,action='gone (an earlier swap removed it)'));continue
    h=dict(pair=f'{a}>{b}',codes=codes,action='unresolved',tries=0,**({'pass':2} if pas else {}));hist.append(h)
    cands=candidates(ctx,cur,i,codes,ban);h['candidates']=len(cands);deeper=[];pads=[];best=[None];av_a=_avoid(cur[i].get('out_win'),codes)
    def attempt(lst,depth):
      for cost,move,c,P in lst:
        sig=json.dumps([(p['id'],p.get('out_win')) for p in P])
        if sig in tried:continue
        tried.add(sig)
        if n[0]>=max_dry or time.time()-t0>budget_s:h['action']='budget';return None
        r=dry(P);h['tries']+=1;fl={k for k,v in (r.get('tests') or {}).items() if not v}
        log(f"  {a}>{b} {move} {c} cost {cost:.1f}: all_ok={r.get('all_ok')} len={r.get('len_min')} fails={sorted(fl)} {r.get('error') or ''}")
        if passes(r):h.update(action=move,track=c,order=[p['id'] for p in P],len_min=r['len_min']);return P,r
        sc=(bool(r.get('all_ok')),-len(fl),r.get('len_min') or 0)
        if not r.get('error') and (best[0] is None or sc>best[0][0]):best[0]=(sc,move,c,r)
        new=[(x,y) for x,y,_ in dry_culprits(r)]
        if depth==1 and fl and fl<=PAIR_TESTS and new and (r.get('len_min') or 0)>=MIN_LEN-1:deeper.append((cost,move,c,P,new))
        if depth<3 and not fl and not r.get('error') and MIN_LEN-PAD_MAX<=(r.get('len_min') or 0)<MIN_LEN:pads.append((cost,move,c,P))
      return None
    got=attempt(cands,1)
    while got is None and deeper and h['action']!='budget':
      # depth 2: a near miss that only broke a new pair (vocal/key/see-saw clash names it) gets that pair repaired too
      cost,move,c,P0,pairs=deeper.pop(0);more=[]
      for a2,b2 in pairs:
        j=next((k for k in range(len(P0)-1) if P0[k]['id']==a2 and P0[k+1]['id']==b2),None)
        if j is not None:more+=[(c2+cost,f'{move}+{m2}',f'{c}+{x2}',P2) for c2,m2,x2,P2 in candidates(ctx,P0,j,['dry'],set(ban)|set(pairs)|{(a,b)})[:DEPTH2_K]]
      h['candidates']+=len(more);got=attempt(more,2)
    while got is None and pads and h['action']!='budget':
      # all_ok but a little short of MIN_LEN: lengthen one other blend (a later exit / earlier entry), never the repaired one
      cost,move,c,P0=pads.pop(0);more=[]
      for j in range(len(P0)-1):
        tj,nj=P0[j]['id'],P0[j+1]['id']
        if a in(tj,nj) or b in(tj,nj) or c in(tj,nj):continue
        w0=P0[j]['out_win'];alts=pick(ctx,tj,nj,ia_of(P0,j),(),6)
        for k,(c2,w2) in enumerate(alts):
          if w2!=w0 and _airtime(w2)>_airtime(w0):
            r2=build(ctx,P0,[p['id'] for p in P0],{a:av_a},ban,k,force=tj)
            if r2:more.append((cost+r2[0],f'{move}+pad',f'{c}+{tj}',r2[1]))
      if len(P0)>2:  # or insert an unused crate track somewhere else (bigger shortfalls: a dropped track)
        ids0=[p['id'] for p in P0];un=[t for t in ctx.crate if t not in ids0]
        for j in range(1,len(P0)):
          for t in un:
            r2=build(ctx,P0,ids0[:j]+[t]+ids0[j:],{a:av_a},ban)
            if r2:more.append((cost+r2[0]+MOVEPEN['insert'],f'{move}+pad_insert',f'{c}+{t}',r2[1]))
      more.sort(key=lambda x:x[0]);h['candidates']+=min(len(more),PAD_K);got=attempt(more[:PAD_K],3)
    if got:
      cur,res=got
      for k,(h0,key,cd) in enumerate([(h0,tuple(h0['pair'].split('>')),h0['codes']) for h0 in hist[:-1] if h0['action']=='unresolved' and not h0.get('requeued')]):
        h0['requeued']=True;todo.append((key,cd,1))   # a later fix changed the plan (length, neighbours): give earlier misses one more pass
    best=best[0]
    if h['action'] in('unresolved','budget') and best:h['closest']=dict(move=best[1],track=best[2],all_ok=best[3].get('all_ok'),len_min=best[3].get('len_min'),fails=[k for k,v in (best[3].get('tests') or {}).items() if not v])
  return cur,res,hist
def resolved(hist):
  """every culprit pair fixed; a first-pass miss counts as fixed when its second pass worked"""
  last={}
  for h in hist:last[h['pair']]=h['action']
  return all(v not in('unresolved','budget') for v in last.values())

def loop(plan,culprits,ctx,render,rounds=3,log=print,**kw):
  """render-stage feedback: repair -> render -> the render's failures become the next culprits (every earlier culprit stays banned),
  for at most `rounds` renders. render(plan, round) -> (passed, [(a,b,code)]). Returns (plan, rounds_log, passed)."""
  ban=set();R=[];cur=plan
  for k in range(rounds):
    P,res,hist=repair(cur,culprits,ctx,ban=ban,log=log,tag=f"{kw.get('tag','repair')}{k}_",**{x:v for x,v in kw.items() if x!='tag'})
    ban|={(a,b) for a,b,_ in culprits};R.append(dict(round=k,hist=hist,dry=dict(all_ok=res.get('all_ok'),len_min=res.get('len_min'))))
    if not(passes(res) and resolved(hist)):R[-1]['stop']='repair could not clear every culprit';return P,R,False
    ok,new=render(P,k);R[-1]['render']=dict(passed=ok,culprits=new)
    if ok:return P,R,True
    if not new:R[-1]['stop']='render failed but no failure names a blend';return P,R,False
    cur,culprits=P,new
    W={p['id']:p.get('out_win') for p in P};ctx.badwin|={(a,b,tuple(W[a])) for a,b,_ in new if W.get(a)}
  return cur,R,False

def render08(script,name,gain,nudge,plan_out):
  """render(plan, round) for loop(): writes the round's plan, runs render08.sh (render + guardrails + every pytest), and turns its
  failures into culprits. Round k is named <name>, <name>b, <name>c ..."""
  import subprocess
  def render(P,k):
    sfx='' if k==0 else 'bcdefgh'[k-1];nm=name+sfx;pf=plan_out[:-5]+sfx+'.json'
    json.dump(P,open(pf,'w'),indent=1);print(f'[{time.strftime("%H:%M")}] render round {k}: {nm} from {pf}',flush=True)
    lg=f'_{nm}_render.log'
    with open(lg,'w') as f:rc=subprocess.run(['bash',script,os.path.abspath(pf),nm,f'{nm}.mp3',str(gain),nudge],stdout=f,stderr=subprocess.STDOUT).returncode
    txt=open(lg).read();print(txt[-3000:],flush=True)
    cul=[] if rc==0 else render_culprits(nm,lg)
    os.remove(lg);print(f'render {nm} rc={rc} culprits={cul}',flush=True);return rc==0,cul
  return render

def main():
  import argparse;ap=argparse.ArgumentParser()
  ap.add_argument('--plan',required=True);ap.add_argument('--out',required=True);ap.add_argument('--render',default=None);ap.add_argument('--log',default=None)
  ap.add_argument('--culprit',default='');ap.add_argument('--budget-s',type=float,default=1800);ap.add_argument('--max-dry',type=int,default=150)
  ap.add_argument('--table',default=os.environ.get('PAIR_TABLE','pair_table.json'));ap.add_argument('--crate',default=None);ap.add_argument('--tag',default='repair')
  ap.add_argument('--history',default='',help='earlier renders name[:log],... whose failed windows are never reused')
  ap.add_argument('--rounds',type=int,default=0,help='render rounds (0 = dry repair only)');ap.add_argument('--render-script',default='../mix08/render08.sh')
  ap.add_argument('--render-name',default=None);ap.add_argument('--gain',default='9.3');ap.add_argument('--nudge',default='nudge05n.json')
  A=ap.parse_args()
  import plan_search as PS
  cul=render_culprits(A.render,A.log) if A.render else []
  for x in [x for x in A.culprit.split(',') if x]:
    ab,_,code=x.partition(':');a,b=ab.split('>');cul.append((a,b,code or 'manual'))
  print('culprits:',cul,flush=True)
  T=json.load(open(A.table));cr=open(A.crate).read().split() if A.crate else PS.crate()
  miss=[c for c in cr if c not in T['tracks']]
  if miss:  # crate tracks newer than the cached table: their per-track limits (e_max, anchor) from the same scorer
    X=PS._row_ctx(A.plan,miss);T['tracks'].update({b:{k:v for k,v in t.items() if k!='cuef'} for b,t in X['tr'].items()});print('added to table tracks:',miss,flush=True)
  ctx=Ctx(T,cr,dry=PS.dry,base=A.plan);plan=json.load(open(A.plan))
  for h in [x for x in A.history.split(',') if x]+([f'{A.render}:{A.log or ""}'] if A.render else []):
    nm,_,lg=h.partition(':');ctx.badwin|=render_bad_windows(nm,lg or None)
  print('render-proved bad windows:',sorted(ctx.badwin),flush=True)
  if A.rounds:
    P,R,ok=loop(plan,cul,ctx,render08(A.render_script,A.render_name,A.gain,A.nudge,A.out),A.rounds,tag=A.tag,budget_s=A.budget_s,max_dry=A.max_dry)
    print(json.dumps(dict(passed=ok,rounds=R),indent=1,default=str));sys.exit(0 if ok else 2)
  P,res,hist=repair(plan,cul,ctx,A.budget_s,A.max_dry,tag=A.tag)
  print(json.dumps(dict(hist=hist,all_ok=res.get('all_ok'),len_min=res.get('len_min'),tests=res.get('tests'),warn=res.get('warn')),indent=1))
  if passes(res) and resolved(hist):json.dump(P,open(A.out,'w'),indent=1);print('wrote',A.out)
  else:sys.exit(2)
if __name__=='__main__':main()
