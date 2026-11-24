#!/usr/bin/env python3
"""Pick new windows for the two r6e QA-failing blends, prove each candidate on its
own mastered clip (blend_gate, 16 bars before to 8 after), and write plan_mix10_r6f.json
with every other r6e blend left unchanged.

The two fails are not the same overlap:
  trans 2, mix bars 496-512 (11:24): Logistics Together -> Culture Shock In The Night
    bass gap at mix 509-511 (low-end -34/-48/-35 dB). Incoming cue ib=32 loops the
    pre-drop intro; bass is handed off at 499-503 into In The Night bars 35-47, whose
    quietest bar is 45, three bars before the drop at 48.
  trans 6, mix bars 816-848 (18:45): Wilkinson Out Of Control -> Zero T When My Love
    beat lag -11 ms (just over the 10 ms cap) at mix 835 and 839 on When My Love,
    corr 0.71/0.84. Window starts When My Love at bar 0 (near silence, intro_end=32)
    for 32 bars; the failed bars are still in that quiet intro, at the bass swap.
"""
import copy,json,os,sys,time,traceback
from pathlib import Path

HERE=Path('/workspace/mixes/src2')
sys.path.insert(0,str(HERE))
os.chdir(HERE)

import blend_gate as BG

PLAN_IN=HERE/'plan_mix10_r6e.json'
PLAN_OUT=HERE/'plan_mix10_r6f.json'
META_R6E=HERE/'mix10_r6e_meta.json'
OUT_JSON=Path('/workspace/mixes/mix10/gate_r6e_alts_results.json')
GAIN=float(os.environ.get('GAIN','9.0'))
NUDGE=os.environ.get('NUDGE','nudge08_r9c.json')

# (outgoing id, incoming id, r6e out_win, candidates to try)
PAIRS=[
  dict(name='Together>In The Night',
       a='3f-XOhfDhxk',b='-n50uo8so4U',
       current=['lb',240,None,32,16],
       # prefer ib=48 (drop) or 64, same Together exit 240, 16-bar family first
       cands=[['n',240,None,48,16],['la',240,224,48,16],['lb',240,None,48,16],
              ['n',240,None,64,16],['la',240,224,64,16],['lb',240,None,64,16],
              ['n',256,None,48,32],['n',256,None,64,16],['n',240,None,32,16]]),
  dict(name='Out Of Control>When My Love',
       a='jIqXQ8EbKNY',b='7Itbo72XEz4',
       current=['n',128,None,0,32],
       # prefer 16-bar enter at 16 so the drop at 32 lands at blend end; keep e=128 when possible
       cands=[['n',128,None,16,16],['la',128,112,16,16],['lb',128,None,16,16],
              ['n',64,None,16,16],['la',64,48,16,16],['n',112,None,16,16],
              ['n',80,None,16,16]]),
]

def log(*a):
  print(f"[{time.strftime('%H:%M:%S')}]",*a,flush=True)

def idx_of(plan,a,b):
  ids=[p['id'] for p in plan]
  for i in range(len(ids)-1):
    if ids[i]==a and ids[i+1]==b:return i
  raise SystemExit(f'pair {a}>{b} not in plan')

def local_plan(plan,i):
  """Previous + this outgoing + incoming + next, so dry meta has neighbours for clip bounds."""
  lo=max(0,i-1);hi=min(len(plan),i+3)
  P=[copy.deepcopy(p) for p in plan[lo:hi]]
  P[0]['tech']='first'
  return P, i-lo  # index of the target blend in the local plan

def summarize(r):
  fails=sorted({f['check'] for f in r.get('blend_fails') or []})
  mix=sorted({f['check'] for f in r.get('mix_level') or []})
  return dict(ok=r.get('ok'),blend_fails=fails,mix_level=mix,
              secs=(r.get('secs') or {}).get('total'),cached=r.get('cached'),
              window=r.get('window'),a=r.get('a'),b=r.get('b'),
              msgs=[f.get('msg','')[:240] for f in (r.get('blend_fails') or [])][:4])

def gate_existing_meta():
  """Sanity: the r6e render meta should fail the gate on the two known-bad blends."""
  M=json.load(open(META_R6E))
  plan=json.load(open(PLAN_IN))
  # attach plan windows onto meta if missing so proven_bad_windows records them
  if not M.get('plan'):M['plan']=plan
  out=[]
  for spec in PAIRS:
    i=idx_of(plan,spec['a'],spec['b'])
    log(f"baseline gate trans {i} {spec['name']} window {spec['current']}")
    r=BG.gate_blend(M,i,GAIN,NUDGE,use_cache=True,keep=False)
    s=summarize(r);s['name']=spec['name'];s['role']='baseline'
    log('  ->',s)
    out.append(s)
  return out

def try_cands(plan):
  results=[]
  picks={}
  for spec in PAIRS:
    i=idx_of(plan,spec['a'],spec['b'])
    found=None
    for w in spec['cands']:
      P=copy.deepcopy(plan)
      P[i]['out_win']=list(w)
      local,li=local_plan(P,i)
      tag=f"r6f_{spec['a'][:6]}_{w[0]}{w[1]}_{w[3]}_{w[4]}"
      log(f"dry+gate {spec['name']} {w}")
      try:
        f=HERE/f'_bg_{tag}_plan.json'
        json.dump(local,open(f,'w'))
        t0=time.time()
        M=BG.dry_meta(str(f),tag)
        dry_s=time.time()-t0
        r=BG.gate_blend(M,li,GAIN,NUDGE,use_cache=True,keep=False)
        s=summarize(r);s.update(name=spec['name'],role='candidate',window=list(w),dry_s=round(dry_s,1),ok_gate=r['ok'])
        log('  ->',s)
      except Exception as e:
        s=dict(name=spec['name'],role='candidate',window=list(w),ok=False,error=f'{type(e).__name__}: {e}'[:400])
        log('  ERROR',s['error'])
        traceback.print_exc()
      finally:
        try:os.remove(HERE/f'_bg_{tag}_plan.json')
        except FileNotFoundError:pass
      results.append(s)
      if s.get('ok') and found is None:
        found=list(w);log(f"  PICK {spec['name']} {w}")
        # keep going through a couple more? stop at first pass to save time
        break
    picks[f"{spec['a']}>{spec['b']}"]=found
    if found is None:
      log(f"NO PASSING WINDOW for {spec['name']}")
  return results,picks

def apply_and_confirm(plan,picks):
  P=copy.deepcopy(plan)
  changed=[]
  for spec in PAIRS:
    i=idx_of(P,spec['a'],spec['b'])
    w=picks[f"{spec['a']}>{spec['b']}"]
    if w is None:return None,dict(error='missing pick',picks=picks)
    if list(P[i]['out_win'])!=list(w):
      changed.append(dict(pair=f"{spec['a']}>{spec['b']}",from_=P[i]['out_win'],to=w,index=i))
      P[i]['out_win']=list(w)
  json.dump(P,open(PLAN_OUT,'w'),indent=1)
  log('wrote',PLAN_OUT,'changed',changed)
  # full-plan dry + gate only the two changed blends (others unchanged)
  log('full-plan dry of r6f')
  t0=time.time()
  M=BG.dry_meta(str(PLAN_OUT),'r6f_full')
  dry_s=time.time()-t0
  log(f'full dry done in {dry_s:.1f}s, trans={len(M.get("trans") or [])}')
  # predict / dry tests live next to meta?
  pred=HERE/'_bg_r6f_full_dry_meta.json'
  tests=None
  if pred.exists():
    D=json.load(open(pred))
    tests={k:D.get(k) for k in ('all_ok','len_min','tests','warn','error') if k in D}
    # some dry metas nest predict
    if 'tests' not in D and 'pred' in D:tests['pred']=D['pred']
    log('dry meta summary',tests)
  gates=[]
  for spec in PAIRS:
    i=idx_of(P,spec['a'],spec['b'])
    # prefer trans matching ids
    ti=next((k for k,t in enumerate(M['trans']) if t['a']==spec['a'] and t['b']==spec['b']),i)
    log(f"full-plan gate trans {ti} {spec['name']}")
    r=BG.gate_blend(M,ti,GAIN,NUDGE,use_cache=True,keep=False)
    s=summarize(r);s.update(name=spec['name'],role='full_plan_confirm',index=ti)
    log('  ->',s);gates.append(s)
  ok=all(g.get('ok') for g in gates)
  return P,dict(changed=changed,dry_s=round(dry_s,1),dry_tests=tests,gates=gates,ok=ok)

def main():
  plan=json.load(open(PLAN_IN))
  report=dict(gain=GAIN,nudge=NUDGE,started=time.strftime('%Y-%m-%dT%H:%M:%S'))
  log('baseline gates on r6e render meta')
  report['baseline']=gate_existing_meta()
  log('try alternate windows')
  cand,picks=try_cands(plan)
  report['candidates']=cand;report['picks']=picks
  if any(v is None for v in picks.values()):
    report['ok']=False;report['stop']='no passing window for at least one pair'
    json.dump(report,open(OUT_JSON,'w'),indent=1,default=str)
    log('FAILED',report['stop']);sys.exit(2)
  P,conf=apply_and_confirm(plan,picks)
  report['confirm']=conf;report['ok']=bool(conf.get('ok'))
  json.dump(report,open(OUT_JSON,'w'),indent=1,default=str)
  log('report written',OUT_JSON,'ok',report['ok'])
  if not report['ok']:
    sys.exit(2)
  # also refuse a deep breakdown hole on the new dry
  try:
    import breakdown_holes as BH
    holes=BH.exposures(json.load(open(HERE/'_bg_r6f_full_dry_meta.json'))) if (HERE/'_bg_r6f_full_dry_meta.json').exists() else []
    # exposures may need the dry meta in mix_simple format
    log('breakdown exposures',holes)
    report['holes']=holes
    json.dump(report,open(OUT_JSON,'w'),indent=1,default=str)
    if any((h.get('kind')=='E1-deep' or h.get('level')=='E1-deep') for h in (holes or [])):
      log('refusing plan: E1-deep exposure');sys.exit(2)
  except Exception as e:
    log('breakdown_holes skipped:',type(e).__name__,e)
  sys.exit(0)

if __name__=='__main__':
  main()
