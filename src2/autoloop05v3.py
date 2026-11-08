"""Mix 05 v2 loop, the listener 2026-11-01 'never stuck, my ears override': render best plan -> guardrails; at most ROUNDS rounds
(stop when no improvement); no window bans (planner costs are soft, only A1 abrupt fade is hard); failing blends get 2-3
alternative snippets written to deliver/ab/pending.json; delivered ONLY if guardrails + pytest pass; otherwise ESCALATE.json + A/B options, ask the listener (17:15 ET)."""
import blend_card as BC
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
  if sh(f"python3 restore_audio.py >/dev/null && python3 mix_simple.py --plan {plan} --out {name} > {LOG}/{name}_render.log 2>&1 && bash ../src/master.sh {name}_raw.wav {LOG}/{name}.mp3 9.3 {name}_master.wav >> {LOG}/{name}_render.log 2>&1"):return None
  sh(f"python3 ../src/guardrails.py --name {name} --mp3 {LOG}/{name}.mp3 --nudge nudge05n.json --png >> {LOG}/{name}_render.log 2>&1")
  G=json.load(open(f'guard_{name}/guardrails.json'));log(f"{name} ({plan}): {G['n_fail']} guardrail fails {G['by_check']}");return G
best=None;cand=None;PT={};START=int(os.environ.get('START',0))
# the listener 2026-11-01 final framing: no defaults/anchors. Every blend: candidates (engine families + Mix 05 window + current + diagnose strategy),
# rendered + tested + scored by the learned A/B model (blend_loop.py), best wins; the full mix is planned with those picks, rendered, tested,
# diagnosed; failing blends go round again (<=ROUNDS); close calls -> A/B.
import blend_loop,diagnose
_O=env.split('ORDER=')[1].split()[0].split(',');PAIRS=[f'{x}>{y}' for x,y in zip(_O,_O[1:])]
_P0=json.load(open('plan_mix05v2i18.json'));CUR={f"{p['id']}>{q['id']}":p.get('out_win') for p,q in zip(_P0,_P0[1:])};CH={};LO=set();todo=list(PAIRS);extra={}
env=env.replace("PINW='"+env.split("PINW='")[1].split("'")[0]+"'","") if "PINW='" in env else env  # gold is a candidate like any other
NJ=f'{LOG}/nudges.jsonl'
FLAGX=set();RENDERED=[];ALLREP={}
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
  elif r>0 and os.environ.get('REUSE0') and os.path.exists(f'{LOG}/blend_loop_{r}.json') and sorted(x['pair'] for x in json.load(open(f'{LOG}/blend_loop_{r}.json'))['pairs'])==sorted(todo):
    rep=json.load(open(f'{LOG}/blend_loop_{r}.json'));picks={x['pair']:x['win'] for x in rep['pairs'] if x['win']}
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
    P0=json.load(open('_ps_1.json'));ids=[p['id'] for p in P0];ALLREP.update({x['pair']:x for x in rep['pairs']});C2=ALLREP;tried={}
    for _it in range(60):
      json.dump(P0,open('_ps_fix.json','w'));q=subprocess.run(f"{env} python3 mix_simple.py --plan _ps_fix.json --out _ps_fix --dry",shell=True,capture_output=True,text=True)
      if q.returncode==0:break
      m=re.search(r"plan window (.*) for (\S+)>(\S+) is no longer allowed",q.stderr)
      if not m:log('repair: mix_simple failed: '+(q.stderr.strip().splitlines() or ['?'])[-1]);P0=None;break
      k=m.group(2)+'>'+m.group(3);i=ids.index(m.group(2))
      # the listener's A/B winners survive: repair the chain around them (previous pair's window sets the incoming entry bar)
      if C2.get(k,{}).get('pick')=='human_ab' and i>0 and P0[i].get('out_win')==C2[k]['win']:
        kp=ids[i-1]+'>'+ids[i];tried.setdefault(kp,[]).append(P0[i-1].get('out_win'))
        nxp=[c[1] for c in sorted(C2.get(kp,{}).get('cands',[]),key=lambda c:(bool(c[3] or c[4]),c[2])) if c[1] not in tried[kp]]
        if nxp:
          P0[i-1]['out_win']=nxp[0];log(f"repair around the listener's pick {k[:4]}>{k.split('>')[1][:4]}: neighbour {kp[:4]}>{kp.split('>')[1][:4]} -> {nxp[0]}")
          with open(NJ,'a') as f:f.write(json.dumps(dict(src='chain_repair',round=r,pair=kp,from_win=tried[kp][-1],win=nxp[0],rescued_by='keep human_ab '+k,ts=time.strftime('%H:%M')+' ET'))+'\n')
          continue
      tried.setdefault(k,[]).append(P0[i].get('out_win'))
      nxt=[c[1] for c in sorted(C2.get(k,{}).get('cands',[]),key=lambda c:(bool(c[3] or c[4]),c[2])) if c[1] not in tried[k]]
      if nxt:P0[i]['out_win']=nxt[0];why='next bench candidate'
      else:P0[i].pop('out_win',None);why='engine best (flagged)';FLAGX.add(k)
      log(f"repair {k[:4]}>{k.split('>')[1][:4]}: {tried[k][-1]} invalid in chain -> {P0[i].get('out_win','engine choice')} ({why})")
      with open(NJ,'a') as f:f.write(json.dumps(dict(src='chain_repair',round=r,pair=k,from_win=tried[k][-1],win=P0[i].get('out_win'),rescued_by=why,ts=time.strftime('%H:%M')+' ET'))+'\n')
    # length floor: if the chain is under 56 min, swap in longer (>=32-bar) strict-passing candidates, cheapest cost increase first
    MINS=float(os.environ.get('MIN_LEN_S',56*60))
    def _len():
      json.dump(P0,open('_ps_fix.json','w'));z=subprocess.run(f"{env} python3 mix_simple.py --plan _ps_fix.json --out _ps_fix --dry",shell=True,capture_output=True,text=True)
      return json.load(open('_ps_fix_dry_meta.json'))['len_sec'] if z.returncode==0 else None
    L=_len() if P0 is not None and q.returncode==0 else None
    if L is not None:
      sw=[]
      for i in range(len(P0)-1):
        k=ids[i]+'>'+ids[i+1];x=C2.get(k,{})
        if x.get('pick')=='human_ab':continue
        for c in x.get('cands',[]):
          if not(c[3] or c[4]) and c[1][4]>=32 and c[1]!=P0[i].get('out_win'):sw.append((c[2]-(x.get('cost') or 0),i,k,c[1]))
      for d,i,k,w in sorted(sw):
        if L>=MINS:break
        old_=P0[i].get('out_win');P0[i]['out_win']=w;L2=_len()
        if L2 is None or L2<=L:P0[i]['out_win']=old_;continue
        log(f"length {L/60:.1f} min < {MINS/60:.0f}: {k[:4]}>{k.split('>')[1][:4]} {old_} -> {w} (+{d:.2f} cost) = {L2/60:.1f} min");L=L2
        with open(NJ,'a') as f:f.write(json.dumps(dict(src='length_fill',round=r,pair=k,from_win=old_,win=w,rescued_by='longer blend',ts=time.strftime('%H:%M')+' ET'))+'\n')
      log(f"chain length {L/60:.1f} min"+(' (still under floor, FLAGGED)' if L<MINS else ''))
    if P0 is not None and q.returncode==0 and L is not None and L>=MINS:json.dump(P0,open(plan,'w'),indent=1);CH.update({f"{p['id']}>{n['id']}":p['out_win'] for p,n in zip(P0,P0[1:]) if p.get('out_win')})
    for _f in glob.glob('_ps_*'):os.remove(_f)
  if not os.path.exists(plan):
    log(f'round {r}: picked blends do not chain into a 56-63 min plan, re-planning with picks as candidates only (unpinned)')
    rc=sh(f"{env} SOFT=0 python3 plan_search.py search --base plan_mix05v2_base.json --out {plan} --min 56 --max 63 --verify 100 --beam 600 >> {LOG}/{name}_search.log 2>&1",t=int(os.environ.get('SEARCH_T',4200)))
  # 2026-11-01 17:15 ET listener: no SOFT=1 fallback; no strict plan -> escalate below
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
  # pytest gates every round (abrupt-fade rule absolute); a round only counts if it passes guardrails AND pytest
  prc=sh(f"DROP_FRAC=0.25 MIX_NAME={name} MIX_MP3={LOG}/{name}.mp3 MIX_WAV=/workspace/mixes/src2/{name}_master.wav python3 -m pytest -q -p no:cacheprovider ../src/tests ../src/build_qa > {LOG}/{name}_pytest.log 2>&1")
  PT[name]=(prc,open(f'{LOG}/{name}_pytest.log').read());log(f"round {r} pytest rc {prc}: {PT[name][1].strip().splitlines()[-1]}")
  if not D['regression'] and (cand is None or (prc!=0,G['n_fail'])<(PT[cand[0]][0]!=0,cand[1]['n_fail'])):cand=(name,G,plan)
  if not D['regression'] and G['n_fail']==0 and prc==0:best=(name,G,plan);break
  if G['n_fail']==0 or not todo:break
# 2026-11-01 17:15 ET listener: pytest gates delivery; if nothing passes, STOP and ASK (ESCALATE.json + rendered A/B options). Never deliver a failing mix.
import blend_bench as BB,shutil
if best is not None:
  name,G,plan=best;shutil.copy(f'{LOG}/{name}.mp3',MP3);open(f'{LOG}/FINAL_NAME','w').write(f'{name} {plan}')
  log(f'pytest exit 0: {name} passes guardrails + pytest')
  sh(f'python3 ../src/deliver.py 05-v2 /workspace/mixes/src2/{name}_meta.json {MP3} "Mix 05 v2"');sh(f'bash ../src/cleanup_after_build.sh >> {R}/deliver/cleanup.log 2>&1');log('delivered');sys.exit(0)
if cand is None:
  why='no strict plan could be built' if not RENDERED else 'every rendered round shows an engine REGRESSION'
  json.dump(dict(date=time.strftime('%Y-%m-%d %H:%M')+' ET',status='NEEDS_DAVID',why=why,rounds=RENDERED),open(f'{LOG}/ESCALATE.json','w'),indent=1);log(why+': escalated, not delivered');sys.exit(2)
name,G,plan=cand;M=json.load(open(f'{name}_meta.json'));T=M['trans'];BAR=M['bar_sec'];ids=[p['id'] for p in M['plan']]
fl={}
for f in G['failures']:
  i=f.get('trans',f.get('trans_guess'))
  if i is None:i=diagnose.trans_of(f,name)
  fl.setdefault(i,[]).append(dict(test='guardrail '+f['check'],why=str(f.get('msg',''))[:200]))
txt=PT[name][1];import re as _re
for m in _re.finditer(r'^FAILED \S+::(\S+)',txt,_re.M):
  tn=m.group(1);blk=txt[txt.find('_ '+tn):] if ('_ '+tn) in txt else '';err=[l for l in blk.splitlines() if l.startswith('E ')][:1]
  hit=[i for i,t in enumerate(T) if t['a'] in (err[0] if err else '')]
  for i in hit or [None]:fl.setdefault(i,[]).append(dict(test='pytest '+tn,why=(err[0][1:].strip() if err else '')[:300]))
AB=f'{R}/deliver/ab/escalate';shutil.rmtree(AB,ignore_errors=True);os.makedirs(AB);os.makedirs(BB.SCR,exist_ok=True);items=[]
P_={p['id']:p for p in M['plan']}
for k,(i,fails) in enumerate(sorted(fl.items(),key=lambda x:(x[0] is None,x[0] or 0)),1):
  if i is None:items.append(dict(n=k,mix_time=None,pair=None,failed=fails,options=[],note='mix-wide test, not tied to one blend'));continue
  t=T[i];a,b=t['a'],t['b'];opts=[]
  try:
    C=BB.families(BB.cands_for(a,b,f'esc{k}'),P_.get(a,{}).get('out_win'))
    cur=[c for c in C if c['is_rated']][:1];alt=[c for c in C if not c['is_rated'] and c['win']!=(cur[0]['win'] if cur else None)][:2]
    for L,c,kind in zip('ABC',cur+alt,['accept flagged version (what the mix has now)']+[f"try strategy {c['fam']}" for c in alt]):
      BB.render(c,a,b,f'esc{k}{L}');dst=f'{AB}/esc{k}_{a}_to_{b}_{L}.mp3';BC.publish(c['mp3'],dst,c.get('timing'));opts.append(dict(opt=L,action=kind,file=dst,win=c['win']))
    if i+2<len(ids):  # drop the incoming track: outgoing straight into the one after it
      c2=ids[i+2];D2=BB.families(BB.cands_for(a,c2,f'esc{k}D'),None)
      if D2:BB.render(D2[0],a,c2,f'esc{k}D');dst=f'{AB}/esc{k}_{a}_to_{c2}_D_drop_{b}.mp3';BC.publish(D2[0]['mp3'],dst,D2[0].get('timing'));opts.append(dict(opt='D',action=f'drop {b}: {a} straight into {c2} ({D2[0]["fam"]})',file=dst,win=D2[0]['win']))
  except Exception as ex:opts.append(dict(error=str(ex)[:300]))
  items.append(dict(n=k,mix_time=time.strftime('%M:%S',time.gmtime(t['start_bar']*BAR)),pair=f'{a}>{b}',failed=fails,options=opts))
shutil.rmtree(BB.SCR,ignore_errors=True)
json.dump(dict(date=time.strftime('%Y-%m-%d %H:%M')+' ET',status='NEEDS_DAVID',mix=name,len_min=round(M['len_sec']/60,2),guardrail_fails=G['n_fail'],
  pytest=PT[name][1].strip().splitlines()[-1],note='not delivered; the listener picks an option per blend, then the loop re-renders with his picks',items=items),open(f'{LOG}/ESCALATE.json','w'),indent=1)
log(f'ESCALATE: {name} fails tests ({G["n_fail"]} guardrail, pytest rc {PT[name][0]}); {len(items)} items in mix05v2/ESCALATE.json; NOT delivered')
sys.exit(3)
