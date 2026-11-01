"""Mix 05 v2 loop, the listener 2026-11-01 'never stuck, my ears override': render best plan -> guardrails; at most ROUNDS rounds
(stop when no improvement); no window bans (planner costs are soft, only A1 abrupt fade is hard); failing blends get 2-3
alternative snippets written to deliver/ab/pending.json; the best full mix is delivered either way, flagged blends listed."""
import os,sys,json,subprocess,time,glob,re
os.environ['NUDGE']='nudge05n.json'  # root cause G1/F1: renders used no warp nudges (nudge.json absent) while guardrails measured with nudge05n
os.chdir('/workspace/mixes/src2');R='/workspace/mixes';P=f'{R}/PROGRESS_mix06.md';LOG=f'{R}/mix05v2'
def log(m):open(P,'a').write(f"- {time.strftime('%H:%M')} ET: [05v3] {m}\n");print(m,flush=True)
def sh(c,t=None):
  try:return subprocess.run(c,shell=True,timeout=t).returncode
  except subprocess.TimeoutExpired:return 124
MP3=f'{LOG}/dj-mix-05-v2.mp3';ROUNDS=int(os.environ.get('ROUNDS',3))
env=open('autoloop05v2.py').read().split("env='")[1].split("'\nBAR")[0].replace("\\'","'")
def render(name,plan):
  sh(f'rm -f {name}_raw.wav {name}_master.wav')
  if sh(f"python3 restore_audio.py >/dev/null && python3 mix_simple.py --plan {plan} --out {name} > {LOG}/{name}_render.log 2>&1 && bash ../src/master.sh {name}_raw.wav {MP3} 9.3 {name}_master.wav >> {LOG}/{name}_render.log 2>&1"):return None
  sh(f"python3 ../src/guardrails.py --name {name} --mp3 {MP3} --nudge nudge05n.json --png >> {LOG}/{name}_render.log 2>&1")
  G=json.load(open(f'guard_{name}/guardrails.json'));log(f"{name} ({plan}): {G['n_fail']} guardrail fails {G['by_check']}");return G
best=None;START=int(os.environ.get('START',0))
# the listener 2026-11-01 final framing: no defaults/anchors. Every blend: candidates (engine families + Mix 05 window + current + diagnose strategy),
# rendered + tested + scored by the learned A/B model (blend_loop.py), best wins; the full mix is planned with those picks, rendered, tested,
# diagnosed; failing blends go round again (<=ROUNDS); close calls -> A/B.
import blend_loop,diagnose
_O=env.split('ORDER=')[1].split()[0].split(',');PAIRS=[f'{x}>{y}' for x,y in zip(_O,_O[1:])]
_P0=json.load(open('plan_mix05v2i18.json'));CUR={f"{p['id']}>{q['id']}":p.get('out_win') for p,q in zip(_P0,_P0[1:])};CH={};LO=set();todo=list(PAIRS);extra={}
env=env.replace("PINW='"+env.split("PINW='")[1].split("'")[0]+"'","") if "PINW='" in env else env  # gold is a candidate like any other
NJ=f'{LOG}/nudges.jsonl'
FLAGX=set();RENDERED=[]
for r in range(ROUNDS):
  name=f'mix05v3r{r}'
  if r<START:continue
  t0=time.time()
  if r==0 and os.environ.get('REUSE0') and os.path.exists(f'{LOG}/blend_loop_0.json'):  # reuse round-0 renders, re-apply human A/B overrides
    rep=json.load(open(f'{LOG}/blend_loop_0.json'));HP=blend_loop.human_picks()
    for x in rep['pairs']:
      _w={tuple(w['w']):w for w in blend_loop.TABLE.get(x['pair'],{}).get('wins',[])}.get(tuple(HP[x['pair']]['win'])) if x['pair'] in HP else None
      if _w and blend_loop.strict_ok(x['pair'],_w):x.update(pick='human_ab',win=HP[x['pair']]['win'],lead_off=False,flagged=False,note='the listener A/B winner (override; strict test at full render)')
    picks={x['pair']:x['win'] for x in rep['pairs'] if x['win']}
  else:picks,rep=blend_loop.run(todo,CUR,extra,tag=f'r{r}_',regress=PAIRS[:3] if r==0 else ())
  json.dump(rep,open(f'{LOG}/blend_loop_{r}.json','w'),indent=1,default=float)
  with open(NJ,'a') as f:
    for x in rep['pairs']:f.write(json.dumps(dict(src='blend_loop',round=r,pair=x['pair'],strategy=x['pick'],rescued_by=(x['pick'] if not x['flagged'] and x['win']!=CUR.get(x['pair']) else None),flagged=x['flagged'],n_pass=x['n_pass'],win=x['win'],lead_off=x['lead_off'],cost=x['cost'],from_win=CUR.get(x['pair']),mix05_rank=x['mix05_rank'],margin=x['margin'],ts=time.strftime('%H:%M')+' ET'),default=float)+'\n')
  CH.update(picks);LO|={x['pair'] for x in rep['pairs'] if x['lead_off']};LO-={x['pair'] for x in rep['pairs'] if not x['lead_off']}
  os.environ['BASS_LEAD_OFF']=','.join(sorted(LO))
  log(f"round {r}: blend loop {len(todo)} blends in {time.time()-t0:.0f}s; picks "+', '.join(f"{x['pair'][:4]}>{x['pair'].split('>')[1][:4]} {x['pick']}{' FLAGGED' if x['flagged'] else ''}" for x in rep['pairs'])+f"; {len(rep['near_ab'])} close calls, {len(rep['regress_ab'])} regression A/B")
  plan=f'plan_{name}.json'
  if os.path.exists(plan):os.remove(plan)
  # 2026-11-01 15:20 ET: picks are scored in a 2-track bench, so a pick can be invalid in the full chain (incoming track entered at a
  # different bar). Chain the picks once (all pairs pinned, table targets skipped), then repair in context with mix_simple --dry:
  # an invalid pick falls to that pair's next passing bench candidate, then to the engine's own best window (logged, flagged).
  for _f in glob.glob('_ps_*'):os.remove(_f)
  rc=sh(f"{env} PINW='{json.dumps(CH)}' SOFT=0 PS_KEEP=1 python3 plan_search.py search --base plan_mix05v2_base.json --out /tmp/_ign.json --min 56 --max 63 --verify 1 --beam 600 > {LOG}/{name}_search.log 2>&1",t=int(os.environ.get('SEARCH_T',4200)))
  if os.path.exists('_ps_1.json'):
    P0=json.load(open('_ps_1.json'));ids=[p['id'] for p in P0];C2={x['pair']:x for x in rep['pairs']};tried={}
    for _it in range(60):
      json.dump(P0,open('_ps_fix.json','w'));q=subprocess.run(f"{env} python3 mix_simple.py --plan _ps_fix.json --out _ps_fix --dry",shell=True,capture_output=True,text=True)
      if q.returncode==0:break
      m=re.search(r"plan window (.*) for (\S+)>(\S+) is no longer allowed",q.stderr)
      if not m:log('repair: mix_simple failed: '+(q.stderr.strip().splitlines() or ['?'])[-1]);P0=None;break
      k=m.group(2)+'>'+m.group(3);i=ids.index(m.group(2));tried.setdefault(k,[]).append(P0[i].get('out_win'))
      nxt=[c[1] for c in sorted(C2.get(k,{}).get('cands',[]),key=lambda c:(bool(c[3] or c[4]),c[2])) if c[1] not in tried[k]]
      if nxt:P0[i]['out_win']=nxt[0];why='next bench candidate'
      else:P0[i].pop('out_win',None);why='engine best (flagged)';FLAGX.add(k)
      log(f"repair {k[:4]}>{k.split('>')[1][:4]}: {tried[k][-1]} invalid in chain -> {P0[i].get('out_win','engine choice')} ({why})")
      with open(NJ,'a') as f:f.write(json.dumps(dict(src='chain_repair',round=r,pair=k,from_win=tried[k][-1],win=P0[i].get('out_win'),rescued_by=why,ts=time.strftime('%H:%M')+' ET'))+'\n')
    if P0 is not None and q.returncode==0:json.dump(P0,open(plan,'w'),indent=1);CH.update({f"{p['id']}>{n['id']}":p['out_win'] for p,n in zip(P0,P0[1:]) if p.get('out_win')})
    for _f in glob.glob('_ps_*'):os.remove(_f)
  if not os.path.exists(plan):
    log(f'round {r}: picked blends do not chain into a 56-63 min plan, re-planning with picks as candidates only (unpinned)')
    rc=sh(f"{env} SOFT=0 python3 plan_search.py search --base plan_mix05v2_base.json --out {plan} --min 56 --max 63 --verify 100 --beam 600 >> {LOG}/{name}_search.log 2>&1",t=int(os.environ.get('SEARCH_T',4200)))
  if not os.path.exists(plan):
    log(f'round {r}: no strict plan; never-die fallback: best-scoring plan, FLAGGED (soft costs only here)')
    rc=sh(f"{env} PINW='{json.dumps(CH)}' SOFT=1 python3 plan_search.py search --base plan_mix05v2_base.json --out {plan} --min 56 --max 63 --verify 100 --beam 600 >> {LOG}/{name}_search.log 2>&1",t=int(os.environ.get('SEARCH_T',4200)))
  if not os.path.exists(plan):log(f'round {r}: no plan (rc {rc}); keeping best so far');break
  G=render(name,plan)
  if G is None:log(f'round {r}: render failed');continue
  RENDERED.append(name);D=diagnose.run(name,r);(diagnose.results(r-1,name,r) if r>0 else None)
  log(f"round {r} diagnose: "+', '.join(f"{o['check']}x{o['n']} {o['cls']}" for o in D['classes'])+(' -- REGRESSION, round blocked from delivery, see mix05v2/diagnose_%d.md'%r if D['regression'] else ''))
  Pn=json.load(open(plan));CUR={f"{p['id']}>{q['id']}":p.get('out_win') for p,q in zip(Pn,Pn[1:])}
  M_=json.load(open(f'{name}_meta.json'));bad=set()
  for o in D['classes']:
    if o['cls']=='FALSE_POS':continue
    for w in o['where']:t=M_['trans'][int(w.split(' trans ')[1].split()[0])];bad.add(f"{t['a']}>{t['b']}")
  todo=sorted(bad);_p,_sl=diagnose.strategies(name,r) if bad and r<ROUNDS-1 else ({},[]);extra={k:[w] for k,w in _p.items()}
  if not D['regression'] and (best is None or G['n_fail']<best[1]['n_fail']):best=(name,G,plan)
  if G['n_fail']==0 or not todo:break
if best is None:
  why='no plan could be built' if not RENDERED else 'every rendered round shows an engine REGRESSION';log(why+': delivery blocked');open(f'{LOG}/BLOCKED','w').write(why);sys.exit(2)
name,G,plan=best;M=json.load(open(f'{name}_meta.json'));T=M['trans'];BAR=M['bar_sec']
fl={}
for f in G['failures']:
  import diagnose;i=f.get('trans',f.get('trans_guess'))
  if i is None:i=diagnose.trans_of(f,name)  # V1 rows carry sec=0 + t_hint; old mapping pinned them all to trans 0
  fl.setdefault(i,[]).append(f['check'])
flags=[dict(t=time.strftime('%M:%S',time.gmtime(T[i]['start_bar']*BAR)),pair=f"{T[i]['a']}>{T[i]['b']}",checks=sorted(set(c))) for i,c in sorted(fl.items())]
# A/B: 2-3 alternatives per flagged blend (current window first), real engine snippets
import blend_bench as BB,shutil;os.makedirs(BB.SCR,exist_ok=True);AB=f'{R}/deliver/ab';os.makedirs(AB,exist_ok=True)
for f in glob.glob(f'{AB}/flag*'):os.remove(f)  # keep near_*/regress_* from blend_loop
items=[];P_={p['id']:p for p in M['plan']}
for k,fx in enumerate(flags,1):
  a,b=fx['pair'].split('>')
  try:
    cs=BB.cands_for(a,b,f'v3_{k}');C=BB.families(cs,P_.get(a,{}).get('out_win'))
    cur=[c for c in C if c['is_rated']][:1];alt=[c for c in C if not c['is_rated'] and c['win']!=(cur[0]['win'] if cur else None)][:2]
    opts={}
    for L,c in zip('ABC',cur+alt):
      BB.render(c,a,b,f'v3_{k}{L}');dst=f"{AB}/flag{k}_{a}_to_{b}_{L}.mp3";shutil.copy(c['mp3'],dst)
      opts[L]=dict(file=dst,fam=c['fam'],win=c['win'],in_mix=c['is_rated'])
    items.append(dict(n=k,mix_time=fx['t'],pair=fx['pair'],failed=fx['checks'],**opts))
  except Exception as ex:items.append(dict(n=k,mix_time=fx['t'],pair=fx['pair'],failed=fx['checks'],error=str(ex)[:300]))
json.dump(dict(date=time.strftime('%Y-%m-%d %H:%M')+' ET',note='blends the tests flagged in the delivered mix; option in_mix=true is what is in the mix now; the listener picks override tests',mix=name,items=items),open(f'{AB}/pending.json','w'),indent=1)
shutil.rmtree(BB.SCR,ignore_errors=True)
log(f'best {name}: {G["n_fail"]} fails; flagged blends '+', '.join(f"{x['t']} {x['pair'][:4]}>{x['pair'].split('>')[1][:4]} {x['checks']}" for x in flags)+f'; {len(items)} A/B sets in deliver/ab/pending.json')
open(f'{LOG}/FINAL_NAME','w').write(f'{name} {plan}');json.dump(flags,open(f'{LOG}/flags_{name}.json','w'),indent=1)
rc=sh(f"DROP_FRAC=0.25 MIX_NAME={name} MIX_MP3={MP3} MIX_WAV=/workspace/mixes/src2/{name}_master.wav python3 -m pytest -q -p no:cacheprovider ../src/tests > {LOG}/{name}_pytest.log 2>&1")
last=open(f'{LOG}/{name}_pytest.log').read().strip().splitlines()[-1]
if rc==0:log(f'pytest exit 0: {last}')  # watch_deliver.sh delivers
else:
  log(f'pytest rc {rc}: {last}; delivering best mix anyway (the listener 2026-11-01), flags listed above')
  sh(f'python3 ../src/deliver.py 05-v2 /workspace/mixes/src2/{name}_meta.json {MP3} "Mix 05 v2"');sh(f'bash ../src/cleanup_after_build.sh >> {R}/deliver/cleanup.log 2>&1');log('delivered (flagged)')
