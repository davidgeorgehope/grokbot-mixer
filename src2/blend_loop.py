"""Per-blend candidate loop (the listener 2026-11-01: 'no defaults or anchors; the original Mix 05 version is one candidate among the options').
For each pair: candidates = engine families (blend_bench.families) + the Mix 05 window on the current engine ('mix05') + the same window on the
Mix 05 engine settings ('mix05_orig': FADE lin, 2-bar swap, no BASS_LEAD/LX_TRIM/LX_PHASE) + the current mix's window ('current') + any
diagnose strategy window ('strategy'). Each is rendered with the real engine (+ master.sh unchanged), measured (W1 see-saw, hard rejects) and
scored with the learned Bradley-Terry weights (eval/blend_bench_results.json). Pick = lowest cost; no special cost for leaving or keeping Mix 05.
Close calls (margin < AB_NEAR) -> A/B list. Also writes regression A/B snippets (Mix 05 render vs new engine) for early Mix 05 blends."""
import json,os,sys,time,shutil,collections
import numpy as np
import blend_bench as BB
R='/workspace/mixes';M06={'FADE':'tail','FADE_DB':'30','BASS_SWAP_BARS':'4','BASS_LEAD':'0','LX_TRIM':'0','LX_PHASE':'0'}  # Mix 06 i12 engine (built 10-31 15:59 ET, code between backups a6f4ae2 and bbe78e2; meta eq_mode)
OLD={'FADE':'lin','BASS_SWAP_BARS':'2','BASS_LEAD':'0','LX_TRIM':'0','LX_PHASE':'0'}
def _job(x):
  c,a,b,tag=x;old={k:os.environ.get(k) for k in c['env']};os.environ.update(c['env'])
  try:
    dk,M=BB.render(c,a,b,tag);BB.measure(c,dk,M);return c
  except Exception as e:c.update(err=str(e)[-300:],hard=['render error'],feats={k:0 for k in BB.FEATS},w1=[]);return c
  finally:
    for k,v in old.items():
      if v is None:os.environ.pop(k,None)
      else:os.environ[k]=v
TABLE=json.load(open('pair_table_05v2.json'))['pairs'] if os.path.exists('pair_table_05v2.json') else {}
def strict_ok(k,w):
  import plan_search as PS
  return not(w['voc'] or w['both']<PS.BOTHMIN or w['R']<0.2 or w['mel']>PS.MELMAX or w['boff']>PS.BOFFMAX or w['step']>PS.STEPMAX)
def human_picks():
  """the listener's blind A/B winners (ratings.jsonl type=ab): {pair: win}; they beat the model unless they fail a strict test"""
  B=json.load(open(f'{R}/eval/blend_bench_results.json'));H={}
  for l in open(f'{R}/ratings.jsonl'):
    q=json.loads(l)
    if q.get('type')!='ab' or 'winner_fam' not in q:continue
    r=next((r for r in B['pairs'] if r['pair']==q['pair']),None)
    c=next((c for c in r['cands'] if (c['is_rated'] if q['winner_fam']=='rated' else c['fam']==q['winner_fam'])),None) if r else None
    if c:H[q['pair']]=dict(win=c['win'],fam=q['winner_fam'],env=c.get('env') or {},sneak=bool(c.get('sneak')))
  return H
def run(pairs,cur_wins,extra=None,tag='bl',jobs=4,regress=()):
  """pairs: ['a>b']; cur_wins {pair:win} (current mix); extra {pair:[win,...]} strategy windows. returns picks {pair:win}, report"""
  os.makedirs(BB.SCR,exist_ok=True);M5=json.load(open('mix05n_meta.json'))['plan'];ids=[p['id'] for p in M5]
  W5={f'{a}>{b}':p['out_win'] for p,a,b in zip(M5,ids,ids[1:]) if p.get('out_win')}
  HP=human_picks();BT=np.array(json.load(open(f'{R}/eval/blend_bench_results.json'))['w']);todo=[];C={}
  for i,k in enumerate(pairs):
    a,b=k.split('>')
    try:cs=BB.families(BB.cands_for(a,b,f'{tag}{i}'),None)
    except Exception as e:cs=[];print('cands_for failed',k,e,flush=True)
    seen={(tuple(c['win']),json.dumps(c['env'],sort_keys=True),bool(c.get('sneak'))) for c in cs}
    def add(fam,win,env={}):
      key=(tuple(win),json.dumps(env,sort_keys=True),False)
      if win and key not in seen:seen.add(key);cs.append(dict(fam=fam,win=win,env=dict(env),is_rated=False))
      elif win:[c.setdefault('also',[]).append(fam) for c in cs if (tuple(c['win']),json.dumps(c['env'],sort_keys=True),bool(c.get('sneak')))==key]
    # wider option set (listener: 'more options', strict filters): table windows that pass the strict planner filters, best per option class
    T=TABLE.get(k,{}).get('wins',[]);strict=[w for w in T if strict_ok(k,w)];per={}
    for w in sorted(strict,key=lambda w:w['pen']):
      kind,e,p,ib,X=w['w'];cls=('lx' if kind=='lx' else 'loop_'+kind if kind!='n' else 'natural',X,'intro_cue' if ib<=16 else 'late_cue')
      if cls not in per:per[cls]=w['w']
    for cls,w in list(per.items())[:int(os.environ.get('BL_WIDE',8))]:add('opt_'+'_'.join(map(str,cls)),w)
    if k in HP:add('human_ab',HP[k]['win'])
    if k in W5:add('mix05',W5[k]);add('mix05_orig',W5[k],OLD);add('mix05_nolead',W5[k],{'BASS_LEAD':'0'})
    _P6=json.load(open(f'{R}/src2/plan_mix06i12.json'));W6={f"{p['id']}>{q['id']}":p.get('out_win') for p,q in zip(_P6,_P6[1:]) if p.get('out_win')}
    if k in W6:add('mix06',W6[k]);add('mix06_orig',W6[k],M06)
    if cur_wins.get(k):add('mix06cfg_current',cur_wins[k],M06)
    if cur_wins.get(k):add('current',cur_wins[k]);add('current_nolead',cur_wins[k],{'BASS_LEAD':'0'})
    for w in (extra or {}).get(k,[]):add('strategy',w)
    C[k]=cs;todo+=[(c,a,b,f'{tag}{i}c{j}') for j,c in enumerate(cs)]
  from concurrent.futures import ProcessPoolExecutor
  with ProcessPoolExecutor(jobs) as ex:res=list(ex.map(_job,todo))
  it=iter(res);picks={};rep=[]
  for k in pairs:
    cs=[next(it) for _ in C[k]]
    for c in cs:c['cost']=round(BB.cost(c,BT)+2.0*len(c.get('w1',[])),3)  # learned A/B model + snippet see-saw test
    cs.sort(key=lambda c:c['cost']);C[k]=cs
    import hashlib
    for c in cs:c['h']=hashlib.md5(open(c['mp3'],'rb').read()).hexdigest() if 'mp3' in c else c['fam']
    ok=[c for c in cs if set(c['env'])<={'BASS_LEAD'} and not c.get('sneak')]  # realisable in the full render: plain windows, BASS_LEAD per pair (BASS_LEAD_OFF)
    rowW={tuple(w['w']):w for w in TABLE.get(k,{}).get('wins',[])}
    for c in cs:c['passes']=bool(not c.get('hard') and not c.get('w1') and not c.get('feats',{}).get('vocal') and tuple(c['win']) in rowW and strict_ok(k,rowW[tuple(c['win'])]))
    P=[c for c in ok if c['passes']]
    best=(P or ok)[0] if ok else None
    hc=[c for c in P if c['fam']=='human_ab' or 'human_ab' in c.get('also',[])] if k in HP else []
    if hc:best=hc[0]  # the listener's ear overrides the model (only strict tests can veto)
    if best:best['flagged']=not P  # never-die fallback only when no option passes
    if best:picks[k]=best['win'];best['lead_off']=best['env'].get('BASS_LEAD')=='0'
    sec=[c for c in ok[1:] if c['h']!=best['h']][:1] if best else []
    rep.append(dict(pair=k,pick=best and best['fam'],flagged=bool(best and best['flagged']),n_pass=len(P),lead_off=bool(best and best['lead_off']),win=best and best['win'],cost=best and best['cost'],also=best and best.get('also'),
      runner_up=sec and dict(fam=sec[0]['fam'],win=sec[0]['win'],cost=sec[0]['cost']),margin=round(sec[0]['cost']-best['cost'],3) if sec else None,
      mix05_rank=next((n for n,c in enumerate(ok,1) if c['fam']=='mix05' or 'mix05' in c.get('also',[])),None),
      cands=[(c['fam'],c['win'],c['cost'],c.get('w1'),c.get('hard')) for c in cs],_A=best,_B=sec[0] if sec else None))
  AB=f'{R}/deliver/ab';os.makedirs(AB,exist_ok=True);items=[]
  for r in rep:
    if r['margin'] is not None and r['margin']<float(os.environ.get('AB_NEAR',1.0)):
      n=r['pair'].replace('>','_to_')
      for s,c in (('A',r['_A']),('B',r['_B'])):shutil.copy(c['mp3'],f'{AB}/near_{n}_{s}.mp3')
      items.append(dict(pair=r['pair'],why='top two within margin',margin=r['margin'],A=dict(fam=r['_A']['fam'],win=r['_A']['win'],file=f'{AB}/near_{n}_A.mp3'),B=dict(fam=r['_B']['fam'],win=r['_B']['win'],file=f'{AB}/near_{n}_B.mp3')))
  reg=[]
  for k in regress:  # regression check: Mix 05 render settings vs new engine, same window
    cs=C.get(k,[]);o=next((c for c in cs if c['fam']=='mix05_orig'),None);nw=next((c for c in cs if c['fam']=='mix05' or 'mix05' in c.get('also',[])),None)
    if o and nw and 'mp3' in o and 'mp3' in nw:
      n=k.replace('>','_to_');shutil.copy(o['mp3'],f'{AB}/regress_{n}_A.mp3');shutil.copy(nw['mp3'],f'{AB}/regress_{n}_B.mp3')
      reg.append(dict(pair=k,A='Mix 05 engine (original render settings)',B='new engine (BASS_LEAD 4-bar swap, tail fade)',win=nw['win'],cost_A=o['cost'],cost_B=nw['cost'],
        feats_A=o['feats'],feats_B=nw['feats'],files=[f'{AB}/regress_{n}_A.mp3',f'{AB}/regress_{n}_B.mp3']))
  for r in rep:r.pop('_A');r.pop('_B')
  shutil.rmtree(BB.SCR,ignore_errors=True)
  return picks,dict(pairs=rep,near_ab=items,regress_ab=reg)
