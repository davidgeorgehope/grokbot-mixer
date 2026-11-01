"""Mix 05 v2 loop, the listener 2026-11-01 'never stuck, my ears override': render best plan -> guardrails; at most ROUNDS rounds
(stop when no improvement); no window bans (planner costs are soft, only A1 abrupt fade is hard); failing blends get 2-3
alternative snippets written to deliver/ab/pending.json; the best full mix is delivered either way, flagged blends listed."""
import os,sys,json,subprocess,time,glob
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
best=None;plan='plan_mix05v2i18.json'
START=int(os.environ.get('START',0))
for r in range(ROUNDS):
  name=f'mix05v3r{r}'
  if r<START:continue
  if r>0:
    plan=f'plan_{name}.json'
    rc=sh(f"{env} HARDCODES=A1 BADWPEN=40 python3 plan_search.py search --base plan_mix05v2_base.json --out {plan} --min 56 --max 63 --verify 100 --beam 600 > {LOG}/{name}_search.log 2>&1",t=int(os.environ.get('SEARCH_T',4200)))  # search ~33 min + dry-verify <=20 min (NPAR 4)
    if not os.path.exists(plan):log(f'round {r}: search gave no plan in time (rc {rc}); keeping best so far');break
  G=render(name,plan)
  if G is None:log(f'round {r}: render failed');continue
  import diagnose;D=diagnose.run(name,r);G['diag']=D  # investigate every failing render (the listener 2026-11-01)
  log(f"round {r} diagnose: "+', '.join(f"{o['check']}x{o['n']} {o['cls']}" for o in D['classes'])+(' -- REGRESSION, round blocked from delivery, see mix05v2/diagnose_%d.md'%r if D['regression'] else ''))
  if D['regression']:
    continue
  if best is None or G['n_fail']<best[1]['n_fail']:best=(name,G,plan)
  elif r>0:log(f'round {r}: no improvement, stopping');break
  if G['n_fail']==0:break
if best is None:
  log('every round shows an engine REGRESSION: delivery blocked; see mix05v2/diagnose_*.md');open(f'{LOG}/BLOCKED','w').write('regression');sys.exit(2)
name,G,plan=best;M=json.load(open(f'{name}_meta.json'));T=M['trans'];BAR=M['bar_sec']
fl={}
for f in G['failures']:
  import diagnose;i=f.get('trans',f.get('trans_guess'))
  if i is None:i=diagnose.trans_of(f,name)  # V1 rows carry sec=0 + t_hint; old mapping pinned them all to trans 0
  fl.setdefault(i,[]).append(f['check'])
flags=[dict(t=time.strftime('%M:%S',time.gmtime(T[i]['start_bar']*BAR)),pair=f"{T[i]['a']}>{T[i]['b']}",checks=sorted(set(c))) for i,c in sorted(fl.items())]
# A/B: 2-3 alternatives per flagged blend (current window first), real engine snippets
import blend_bench as BB,shutil;os.makedirs(BB.SCR,exist_ok=True);AB=f'{R}/deliver/ab';os.makedirs(AB,exist_ok=True)
for f in glob.glob(f'{AB}/*'):os.remove(f)
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
