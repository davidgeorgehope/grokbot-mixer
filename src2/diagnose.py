"""Auto-diagnose after every render (the listener 2026-11-01: 'guardrail fails can be real bugs; investigate after every failure').
For each failing check class: compare with the last passing mixes (Mix 05 = mix05n, Mix 06 iter 12 = mix06i12) and the backup git
history, then classify: REGRESSION (renderer/engine: new class vs refs at an engine-owned check, or the same fail across >=2 pairs at the
same kind of event), TRADEOFF (soft-cost planner let a weaker window through -> A/B list), or FALSE_POS (test artefact).
Writes mix05v2/diagnose_<round>.md + .json; returns dict(regression=bool, ...). Usage: python3 diagnose.py <name> <round>"""
import json,os,sys,subprocess,collections
R='/workspace/mixes';GIT='/workspace/yt-dj-crate-git';REFS=('mix05n','mix06i12')
ENGINE={'G1','F1','L1','N1','P1','E1','E2','S1','J1'}  # grid/phase/level/bass/tail: what the renderer owns
PLANNER={'V1','R1','O1','C2','W1','K1','E4'}  # window choice: what the soft-cost planner trades
EVKW={'lx':'_lx|LX_|beat-only','loop':'loop','bass_swap':'swap_w|BASS_LEAD|low','echo':'echo','blend':'xfader|gain'}
def G(n):
  p=f'{R}/src2/guard_{n}/guardrails.json';return json.load(open(p)) if os.path.exists(p) else None
def events(n):
  p=f'{R}/src2/{n}_meta.json'
  if not os.path.exists(p):return {}
  M=json.load(open(p));D={d['id']:d for d in M['decks']};ev={}
  for i,t in enumerate(M['trans']):
    a=D.get(t['a'],{});src=[c for _,c in a.get('full_map',[])];bars=[s for s,_ in a.get('full_map',[])]
    ev[i]=('lx' if 'beat' in src else 'loop' if len(bars)!=len(set(bars)) else 'echo' if t.get('echo') or a.get('echo') else 'blend')
  return ev
def trans_of(f,n):
  if 'trans' in f:return f['trans']
  p=f'{R}/src2/{n}_meta.json'
  if not os.path.exists(p):return None
  M=json.load(open(p));B=M['bar_sec'];h=f.get('t_hint') if not f.get('sec') else None
  sec=(lambda s:int(s.split(':')[0])*60+int(s.split(':')[1]))(h) if h else f.get('sec',0)
  return min(range(len(M['trans'])),key=lambda k:abs(sec/B-M['trans'][k]['start_bar']))
def git_log(kw):
  try:return subprocess.run(['git','-C',GIT,'log','--since=2026-10-31 19:00','--format=%h %ad %s','--date=format:%H:%M','-G',kw,'--','grokbot-mixer/src2/engine.py','grokbot-mixer/src2/mix_simple.py','grokbot-mixer/src2/beatstem.py','grokbot-mixer/src2/plan_search.py'],capture_output=True,text=True,timeout=60).stdout.strip().splitlines()[:5]
  except Exception as e:return [f'git log failed: {e}']
def run(name,rnd):
  g=G(name);ev=events(name);refs={r:G(r) for r in REFS};refev={r:collections.Counter(events(r).values()) for r in REFS}
  refcls=collections.Counter(f['check'] for r in refs.values() if r for f in r['failures'])
  by=collections.defaultdict(list)
  for f in g['failures']:t=trans_of(f,name);by[f['check']].append(dict(f,_t=t,_ev=ev.get(t,'?')))
  out=[]
  for c,fs in sorted(by.items()):
    pairs={(f['msg'].split()[0],f['_t']) for f in fs};kinds=collections.Counter(f['_ev'] for f in fs);top,kn=kinds.most_common(1)[0]
    new_kind=top!='?' and all(refev[r].get(top,0)==0 for r in REFS);fp=[]
    if c=='V1' and all(not f.get('sec') and f.get('t_hint') for f in fs):fp.append('V1 rows carry sec=0 (time only in t_hint): flags were pinned to 0:00/trans 0; diagnose re-maps by t_hint. Fix in guardrails V1 output')
    if c=='W1':fp+=[f"{f['t']} W1 wobble-only with outgoing rise {f.get('out_rise')} dB <1 dB: likely FALSE_POS" for f in fs if f.get('out_rise',9)<1 and 'OUT_RISE' not in f['msg']]
    if c in ENGINE and (len({p[1] for p in pairs})>=2 and kn>=2 or refcls.get(c,0)==0 and new_kind):
      cls='REGRESSION'
    elif fp and len(fp)>=len(fs):cls='FALSE_POS'
    else:cls='TRADEOFF'
    kw=EVKW.get(top,'gain');commits=git_log(kw) if cls=='REGRESSION' else []
    out.append(dict(check=c,n=len(fs),cls=cls,event_kind=dict(kinds),new_event_kind=new_kind,in_refs=refcls.get(c,0),
      where=[f"{f['t'] if f.get('sec') else f.get('t_hint',f['t'])} trans {f['_t']} [{f['_ev']}]: {f['msg']}" for f in fs],false_pos_notes=fp,suspect_commits=commits,suspect_code=kw if cls=='REGRESSION' else None))
  AF=f'{R}/mix05v2/anchor_mix05.json';AN=json.load(open(AF)) if os.path.exists(AF) else {}
  if AN and os.path.exists(f'{R}/src2/{name}_meta.json'):
    TT=json.load(open(f'{R}/src2/{name}_meta.json'))['trans']
    for o in out:
      hit=[w for w in o['where'] if f"{TT[int(w.split(' trans ')[1].split()[0])]['a']}>{TT[int(w.split(' trans ')[1].split()[0])]['b']}" in AN]
      if hit and o['cls']!='FALSE_POS':o['cls']='REGRESSION';o['false_pos_notes'].append(f'{len(hit)} fail(s) on Mix 05 anchor blends (same window passed in mix05n): regression vs the original')
  reg=[o for o in out if o['cls']=='REGRESSION']
  md=[f'# diagnose round {rnd}: {name}',f"{g['n_fail']} fails {g['by_check']}; refs " + ', '.join(f"{r} {refs[r]['n_fail'] if refs[r] else '?'} fails" for r in REFS),
      f"**{'REGRESSION SUSPECTED - delivery blocked for this round' if reg else 'no engine regression'}**",'']
  for o in out:
    md+=[f"## {o['check']} x{o['n']} -> {o['cls']}",f"event kinds {o['event_kind']} (new vs refs: {o['new_event_kind']}); in passing refs: {o['in_refs']}"]+[f'- {w}' for w in o['where']]
    md+=[f'- note: {x}' for x in o['false_pos_notes']]+([f"- suspect code /{o['suspect_code']}/ in engine/mix_simple/beatstem; commits: "+('; '.join(o['suspect_commits']) or 'none in backups since Mix 06 i12')] if reg and o in reg else [])+['']
  os.makedirs(f'{R}/mix05v2',exist_ok=True);open(f'{R}/mix05v2/diagnose_{rnd}.md','w').write('\n'.join(md))
  res=dict(name=name,round=rnd,regression=bool(reg),classes=out);json.dump(res,open(f'{R}/mix05v2/diagnose_{rnd}.json','w'),indent=1);return res
if __name__=='__main__':
  r=run(sys.argv[1],sys.argv[2]);print(open(f"{R}/mix05v2/diagnose_{sys.argv[2]}.md").read())
# ---- closed loop (the listener 2026-11-01): per failing blend pick a DIFFERENT strategy, pin it for the next round, log to nudges.jsonl
STRAT={'V1':'vocal-free window: drums+bass outro (lx) > instrumental-intro cue / different phrase (voc=0)',
  'W1':'longer ride / different fade shape (longer X, voc=0)','O1':'longer blend (more both-audible bars)','R1':'tighter drum match (higher R)',
  'C2':'different phrase (other e)','L1':'engine: bass lead (BASS_LEAD)','N1':'engine: gain staging (LX_TRIM)','G1':'engine: lx re-phase','F1':'engine: lx re-phase'}
def strategies(name,rnd,table='pair_table_05v2.json',tried=None,anchor=None):
  """returns {pair: window} pins for the next round (one new strategy per failing pair, never the window that just failed)"""
  D=json.load(open(f'{R}/mix05v2/diagnose_{rnd}.json'));M=json.load(open(f'{R}/src2/{name}_meta.json'));T=json.load(open(f'{R}/src2/{table}'))['pairs']
  OW={p['id']:p.get('out_win') for p in M['plan']};per=collections.defaultdict(set)
  for o in D['classes']:
    if o['cls']=='FALSE_POS':continue
    for w in o['where']:
      t=int(w.split(' trans ')[1].split()[0]);tr=M['trans'][t];per[(tr['a'],tr['b'])].add(o['check'])
  hist=collections.defaultdict(list);FXH=collections.defaultdict(list)
  NJ=f'{R}/mix05v2/nudges.jsonl'
  if os.path.exists(NJ):
    for l in open(NJ):
      try:x=json.loads(l);hist[x.get('pair')].append(x.get('win'));FXH[x.get('pair')].append(x)
      except Exception:pass
  pins={};log=[]
  for (a,b),cs in per.items():
    k=f'{a}>{b}';cur=OW.get(a);W=[w for w in T.get(k,{}).get('wins',[]) if w['w']!=cur and w['w'] not in hist[k] and w['boff']<=2]
    if a=='j9AuFRpLk7U' and b=='cxS6yd0UAxw':continue  # gold pin stays
    if anchor and k in anchor:log.append(dict(pair=k,round=rnd,fails=sorted(cs),strategy='anchor (passed in Mix 05): kept exactly, treated as engine regression, A/B vs original',win=anchor[k],result='anchor'));continue
    eng=[c for c in cs if c in('N1','L1','G1','F1')];mus=[c for c in cs if c not in eng]
    if not mus:log.append(dict(pair=k,round=rnd,fails=sorted(cs),strategy=[STRAT[c] for c in eng],win=None,note='engine fix only, window kept'));continue
    cw=next((w for w in T.get(k,{}).get('wins',[]) if w['w']==cur),None) or dict(both=0,R=0,w=[None,0,None,0,16])
    C=[w for w in W if not w['voc'] and w['both']>=8] or [w for w in W if not w['voc']] or W
    if C:m=min(w['pen'] for w in C);C=[w for w in C if w['pen']<=m+60]  # stay near the best-scoring windows
    # fix playbook (eval/fix_playbook.json): next untried fix per failing check; 'exhausted' -> escalate
    PB=json.load(open(f'{R}/eval/fix_playbook.json'));done_fx={x.get('fix') for x in FXH.get(k,[])}
    def _flt(f,C):
      if f in('longer_ride','longer_blend'):return sorted([w for w in C if w['w'][4]>cw['w'][4] or w['both']>cw['both']],key=lambda w:(-w['w'][4],w['pen']))
      if f=='beat_outro_lx':return [w for w in C if w['w'][0]=='lx']
      if f=='other_cue_phrase':return sorted([w for w in C if w['w'][1]!=cw['w'][1]],key=lambda w:w['pen'])
      if f=='other_in_phrase':return sorted([w for w in C if w['w'][3]!=cw['w'][3]],key=lambda w:w['pen'])
      if f in('natural_no_loop','fade_shape_lin'):return sorted([w for w in C if w['w'][0]=='n'],key=lambda w:w['pen'])
      return []
    fx=None
    for c in sorted(mus):
      for f in PB.get(c,PB['_default'])['fixes']:
        if f in done_fx or f.startswith('engine:'):continue
        C2=_flt(f,C)
        if C2:fx=f;C=C2;break
      if fx:break
    if not fx:C=[]
    if not C:log.append(dict(pair=k,round=rnd,fails=sorted(cs),fix='exhausted',strategy='playbook used up',win=None,note='-> A/B'));continue
    w=C[0];pins[k]=w['w'];log.append(dict(pair=k,round=rnd,fails=sorted(cs),fix=fx,strategy=[STRAT.get(c,c) for c in sorted(cs)],from_win=cur,win=w['w'],voc=w['voc'],both=w['both'],R=round(w['R'],2),pen=w['pen'],result='pending'))
  with open(NJ,'a') as f:
    for x in log:f.write(json.dumps(dict(x,src='closed_loop',ts=__import__('time').strftime('%H:%M')+' ET'))+'\n')
  return pins,log
def results(prev_rnd,name,rnd):
  """after the re-render: append the outcome of each pinned strategy (pass / still failing which checks)"""
  NJ=f'{R}/mix05v2/nudges.jsonl';D=json.load(open(f'{R}/mix05v2/diagnose_{rnd}.json'));M=json.load(open(f'{R}/src2/{name}_meta.json'))
  failing=collections.defaultdict(set)
  for o in D['classes']:
    for w in o['where']:t=int(w.split(' trans ')[1].split()[0]);tr=M['trans'][t];failing[f"{tr['a']}>{tr['b']}"].add(o['check'])
  rows=[json.loads(l) for l in open(NJ)] if os.path.exists(NJ) else []
  with open(NJ,'a') as f:
    for x in rows:
      if x.get('src')=='closed_loop' and x.get('round')==prev_rnd and x.get('result')=='pending':
        f.write(json.dumps(dict(pair=x['pair'],round=rnd,src='closed_loop_result',win=x.get('win'),result='pass' if x['pair'] not in failing else 'still '+','.join(sorted(failing[x['pair']])),in_mix=any(f"{t['a']}>{t['b']}"==x['pair'] for t in M['trans'])))+'\n')
