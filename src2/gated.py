#!/usr/bin/env python3
"""BLEND_AUDIO_GATE wiring for search, repair and render (RCA 2026-11-24). New module on purpose: plan_search.py / repair.py are
used unchanged (repair.Ctx takes the dry function as a parameter; plan_search reads window bans from SEESAW_BANFILE), so a live
job using them is never disturbed. With BLEND_AUDIO_GATE unset, `search` and `repair` refuse to run (use plan_search/repair directly).

  gated.py check  --plan P.json --gain 9.0                     dry + predict (13 dry gates) + every blend's audio gate + solo-hole check
  gated.py search --base B.json --out P.json --pool POOL.json [--search "plan_search search args"] [--rounds 2] [--max-plans 12]
        propose (pool order) -> dry -> gate blends in parallel -> ban the failing windows -> next plan; pool exhausted -> re-run
        plan_search search with the bans (SEESAW_BANFILE = merged ban file) -> repeat. Writes P.json only when everything passes.
  gated.py repair --plan P.json --out Q.json [--render NAME] [repair.py args]
        repair.repair() with ctx.dry = dry AND audio gate: a try passes only if its changed blends pass on their own audio;
        unchanged blends are cache hits. Gate-failing pairs of the start plan become culprits; their windows go to ctx.badwin.
Env: source the mix env first (CRATE_FILE, PAIR_TABLE, engine flags). Ban file: GATE_BANFILE (default blend_gate_bans.json)."""
import os,sys,json,time,subprocess,argparse,shlex
HERE=os.path.dirname(os.path.abspath(__file__));sys.path.insert(0,HERE);os.chdir(HERE)
import blend_gate as BG,breakdown_holes as BH
BANFILE=os.environ.get('GATE_BANFILE',os.path.join(HERE,'blend_gate_bans.json'))
CODEMAP={'test_no_bass_gap_in_overlaps':'bassgap','test_no_level_dip_at_swap':'swapdip','N1':'N1','G1':'N1',
  'test_mixdown_beats_aligned_every_overlap_bar':'beat_aligned','test_beat_drift_across_transitions':'beat_aligned',
  'test_downbeats_aligned':'beat_aligned','test_outgoing_audio_tail_never_drops_abruptly':'tail','E1':'E1','E3':'E1','C2':'tail'}

def load_bans():
  B=json.load(open(BANFILE)) if os.path.exists(BANFILE) else {}
  for a,b,w in BG.proven_bad_windows():
    if list(w) not in B.setdefault(f'{a}>{b}',[]):B[f'{a}>{b}'].append(list(w))
  return B
def add_bans(B,items):
  n=0
  for a,b,w in items:
    if w and list(w) not in B.setdefault(f'{a}>{b}',[]):B[f'{a}>{b}'].append(list(w));n+=1
  json.dump(B,open(BANFILE,'w'),indent=1);return n
def merged_banfile(B):
  """plan_search hard-bans every window listed in SEESAW_BANFILE (bad_windows()); keep the mix's own see-saw bans in it too"""
  m=dict(B);src=os.environ.get('SEESAW_BANFILE_BASE') or os.environ.get('SEESAW_BANFILE')
  if src and os.path.exists(src) and os.path.abspath(src)!=os.path.abspath(BANFILE+'.merged.json'):
    for k,ws in json.load(open(src)).items():
      for w in ws:
        if w not in m.setdefault(k,[]):m[k].append(w)
  p=BANFILE+'.merged.json';json.dump(m,open(p,'w'));return p

def dry_predict(plan,tag):
  """plan_search.dry() (mix_simple --dry + predict on its meta), keeping the meta for the audio gate"""
  import plan_search as PS
  f=f'_gt_{tag}.json';json.dump(plan,open(f,'w'));meta=f'_gt_{tag}_dry_meta.json'
  try:
    r=subprocess.run([sys.executable,'mix_simple.py','--plan',f,'--out',f'_gt_{tag}','--dry'],capture_output=True,text=True)
    if r.returncode:return dict(error=(r.stderr.strip().splitlines() or ['mix_simple failed'])[-1]),None
    p=PS.predict(f'_gt_{tag}_dry');M=json.load(open(meta));return p,M
  except Exception as e:return dict(error=f'{type(e).__name__}: {e}'),None
  finally:
    for x in (f,meta):
      if os.path.exists(x):os.remove(x)

def gate_meta(M,gain,nudge,jobs):
  R=BG.gate_plan(M,gain,nudge,jobs=jobs);fails=[]
  for i,r in sorted(R.items()):
    if not r['ok']:
      w=(M['plan'][i].get('out_win') if i<len(M.get('plan',[])) else None)
      for f in r['blend_fails']:fails.append((r['a'],r['b'],CODEMAP.get(f['check'],'bag'),w,f['check'],r['mix_t']))
  holes=[x for x in BH.exposures(M) if x[0]=='E1-deep']
  return R,fails,holes

def gated_dry(plan,tag,gain,nudge,jobs=3,log=print):
  """dry + audio gate. Returns the predict dict with tests['blend_audio'] / tests['solo_hole'] added and all_ok recomputed."""
  p,M=dry_predict(plan,tag)
  if M is None or not p.get('all_ok'):return p
  R,fails,holes=gate_meta(M,gain,nudge,jobs)
  p['tests']=dict(p['tests'],blend_audio=not fails,solo_hole=not holes);p['all_ok']=all(p['tests'].values())
  p['gate_fails']=[dict(a=a,b=b,code=c,window=w,check=k,t=t) for a,b,c,w,k,t in fails]
  p['solo_holes']=[dict(track=t,bar=b,n=n,src=s[:4]) for _,t,b,n,s in holes]
  p['gate_secs']=round(sum(r['secs']['total'] for r in R.values() if not r.get('cached')),1);p['gate_cached']=sum(bool(r.get('cached')) for r in R.values())
  log(f"[{time.strftime('%H:%M:%S')}] gate {tag}: {'PASS' if not fails and not holes else 'FAIL'} blend fails {[(f['a'][:6],f['b'][:6],f['check']) for f in p['gate_fails']]} "
      f"solo holes {[(h['track'],h['bar']) for h in p['solo_holes']]} ({p['gate_secs']}s new, {p['gate_cached']} cached)",flush=True)
  return p

def _hole_windows(plan,holes):
  """a solo hole is fixed by the blends around that track: ban both of its windows (entry and exit) as planned"""
  ids=[s['id'] for s in plan];out=[]
  for h in holes:
    if h['track'] in ids:
      j=ids.index(h['track'])
      if j>0:out.append((ids[j-1],ids[j],plan[j-1].get('out_win')))
      if j+1<len(ids):out.append((ids[j],ids[j+1],plan[j].get('out_win')))
  return out

def cmd_search(A):
  import plan_search as PS
  B=load_bans();t0=time.time();tried=0;pool_path=A.pool;rounds=0;log=[]
  while True:
    pool=json.load(open(pool_path)) if pool_path and os.path.exists(pool_path) else []
    print(f'[{time.strftime("%H:%M:%S")}] pool {pool_path}: {len(pool)} plans, {sum(len(v) for v in B.values())} banned windows',flush=True)
    seen=set();excl=set(x for x in A.exclude.split(',') if x)
    for d in pool:
      if tried>=A.max_plans:break
      vk=tuple(tuple(w['w']) for w in d['bl'])
      if vk in seen or excl&set(d['seq']):continue
      if any(w['w'] in B.get(f"{w['a']}>{w['b']}",[]) for w in d['bl']):continue
      seen.add(vk);tried+=1;P=PS.to_plan(d,A.base)
      p=gated_dry(P,f's{tried}',A.gain,A.nudge,A.jobs)
      row=dict(n=tried,tests={k:v for k,v in (p.get('tests') or {}).items() if not v},error=p.get('error'),gate_fails=p.get('gate_fails'),holes=p.get('solo_holes'))
      log.append(row);print(f"plan {tried}: {'ALL OK' if p.get('all_ok') else 'fail '+str(list(row['tests']) or row['error'])}",flush=True)
      if p.get('all_ok'):
        json.dump(P,open(A.out,'w'),indent=1);print(json.dumps(dict(plan=A.out,tried=tried,secs=round(time.time()-t0),log=log),default=str));return 0
      nb=add_bans(B,[(f['a'],f['b'],f['window']) for f in p.get('gate_fails') or []]+_hole_windows(P,p.get('solo_holes') or []))
      if nb:print(f'  banned {nb} windows -> {BANFILE}',flush=True)
    if rounds>=A.rounds or not A.search or tried>=A.max_plans:break
    rounds+=1;mb=merged_banfile(B);out=A.out.rsplit('.',1)[0]+f'_gs{rounds}.json'
    cmd=[sys.executable,'plan_search.py','search','--base',A.base,'--out',out]+shlex.split(A.search)
    print(f'[{time.strftime("%H:%M:%S")}] re-search round {rounds} with bans: {" ".join(cmd)}',flush=True)
    r=subprocess.run(cmd,env=dict(os.environ,SEESAW_BANFILE=mb),text=True);pool_path=out.rsplit('.',1)[0]+'.pool.json'
    if not os.path.exists(pool_path):print('re-search wrote no pool (rc',r.returncode,')');break
  print(json.dumps(dict(plan=None,tried=tried,secs=round(time.time()-t0),log=log),default=str));return 2

def cmd_repair(A,rest):
  import repair as RP,plan_search as PS
  sys.argv=['repair.py','--plan',A.plan,'--out',A.out]+rest
  ap=argparse.ArgumentParser();ap.add_argument('--render',default=None);ap.add_argument('--log',default=None);ap.add_argument('--culprit',default='')
  ap.add_argument('--budget-s',type=float,default=10800);ap.add_argument('--max-dry',type=int,default=150);ap.add_argument('--tag',default='grep')
  ap.add_argument('--table',default=os.environ.get('PAIR_TABLE','pair_table.json'));ap.add_argument('--crate',default=None);ap.add_argument('--history',default='')
  R=ap.parse_args(rest)
  cul=RP.render_culprits(R.render,R.log) if R.render else []
  for x in [x for x in R.culprit.split(',') if x]:
    ab,_,code=x.partition(':');a,b=ab.split('>');cul.append((a,b,code or 'manual'))
  T=json.load(open(R.table));cr=open(R.crate).read().split() if R.crate else PS.crate()
  miss=[c for c in cr if c not in T['tracks']]
  if miss:
    X=PS._row_ctx(A.plan,miss);T['tracks'].update({b:{k:v for k,v in t.items() if k!='cuef'} for b,t in X['tr'].items()})
  ctx=RP.Ctx(T,cr,base=A.plan);plan=json.load(open(A.plan))
  def dry(P,tag):
    p=gated_dry(P,tag,A.gain,A.nudge,A.jobs)
    for f in p.get('gate_fails') or []:
      if f['window']:ctx.badwin.add((f['a'],f['b'],tuple(f['window'])))
    return p
  ctx.dry=dry
  for h in [x for x in R.history.split(',') if x]+([f'{R.render}:{R.log or ""}'] if R.render else []):
    nm,_,lg=h.partition(':');ctx.badwin|=RP.render_bad_windows(nm,lg or None)
  ctx.badwin|=BG.proven_bad_windows()
  p0=dry(plan,f'{R.tag}0')   # the start plan's own audio failures become culprits (code per CODEMAP so N1/energy rules apply)
  for f in p0.get('gate_fails') or []:
    if (f['a'],f['b']) not in {(a,b) for a,b,_ in cul}:cul.append((f['a'],f['b'],f['code']))
  print('culprits:',cul,flush=True)
  P,res,hist=RP.repair(plan,cul,ctx,R.budget_s,R.max_dry,tag=R.tag)
  ok=RP.passes(res) and RP.resolved(hist);hp=RP.write_repair_out(A.out,P,res,hist,ok)
  print(json.dumps(dict(hist=hist,all_ok=res.get('all_ok'),tests=res.get('tests'),gate_fails=res.get('gate_fails'),resolved=ok),indent=1,default=str))
  print('wrote',A.out,'and',hp);return 0 if ok else 2

def cmd_check(A):
  P=json.load(open(A.plan));p=gated_dry(P,'chk',A.gain,A.nudge,A.jobs)
  print(json.dumps({k:p.get(k) for k in ('all_ok','tests','gate_fails','solo_holes','gate_secs','gate_cached','error','len_min')},indent=1,default=str))
  return 0 if p.get('all_ok') else 1

if __name__=='__main__':
  ap=argparse.ArgumentParser();ap.add_argument('cmd',choices=['check','search','repair']);ap.add_argument('--plan');ap.add_argument('--out')
  ap.add_argument('--base');ap.add_argument('--pool');ap.add_argument('--search',default='');ap.add_argument('--rounds',type=int,default=1)
  ap.add_argument('--max-plans',type=int,default=12);ap.add_argument('--exclude',default='');ap.add_argument('--gain',type=float,default=9.0)
  ap.add_argument('--nudge',default=os.environ.get('NUDGE','nudge08_r9c.json'));ap.add_argument('--jobs',type=int,default=3)
  A,rest=ap.parse_known_args()
  if A.cmd!='check' and not BG.enabled():sys.exit('BLEND_AUDIO_GATE is off: set BLEND_AUDIO_GATE=1 (or use plan_search.py / repair.py directly)')
  sys.exit({'check':lambda:cmd_check(A),'search':lambda:cmd_search(A),'repair':lambda:cmd_repair(A,rest)}[A.cmd]())
