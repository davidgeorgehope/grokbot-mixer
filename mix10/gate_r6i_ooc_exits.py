#!/usr/bin/env python3
"""Fix (1) for r6h coverage: keep When My Love ib=16, try later legal Out Of Control
exits (96, then already-known 112/128 only if needed) and gate each clip.
Does not start a render or search."""
import copy,json,os,sys,time,traceback
from pathlib import Path

HERE=Path('/workspace/mixes/src2')
sys.path.insert(0,str(HERE))
os.chdir(HERE)
import blend_gate as BG

PLAN_IN=HERE/'plan_mix10_r6e.json'
OUT_JSON=Path('/workspace/mixes/mix10/gate_r6i_ooc_exits_results.json')
GAIN=float(os.environ.get('GAIN','9.0'))
NUDGE=os.environ.get('NUDGE','nudge08_r9c.json')
TOGETHER_WIN=['n',240,None,48,16]
TOGETHER=('3f-XOhfDhxk','-n50uo8so4U')
WML=('jIqXQ8EbKNY','7Itbo72XEz4')
# later legal ib=16, 16-bar exits (104 is not in the pair table). 80 already
# gate-passed but leaves OOC at cov 0.49. 112 and 128 already failed lag_0
# after the sidecar-checker fix; still listed last so we can skip if 96 works.
CANDS=[
  ['n',96,None,16,16],
  ['la',96,80,16,16],
  ['lb',96,None,16,16],
]

def log(*a):
  print(f"[{time.strftime('%H:%M:%S')}]",*a,flush=True)

def idx_of(plan,a,b):
  ids=[p['id'] for p in plan]
  for i in range(len(ids)-1):
    if ids[i]==a and ids[i+1]==b:return i
  raise SystemExit(f'pair {a}>{b} not in plan')

def local_plan(plan,i):
  lo=max(0,i-1);hi=min(len(plan),i+3)
  P=[copy.deepcopy(p) for p in plan[lo:hi]];P[0]['tech']='first'
  return P,i-lo

def summarize(r):
  fails=sorted({f['check'] for f in r.get('blend_fails') or []})
  return dict(ok=r.get('ok'),blend_fails=fails,secs=(r.get('secs') or {}).get('total'),
              cached=r.get('cached'),window=r.get('window'),
              msgs=[f.get('msg','')[:400] for f in (r.get('blend_fails') or [])][:4])

def main():
  plan=json.load(open(PLAN_IN))
  plan[idx_of(plan,*TOGETHER)]['out_win']=list(TOGETHER_WIN)
  iW=idx_of(plan,*WML)
  results=[];pick=None
  for w in CANDS:
    P=copy.deepcopy(plan);P[iW]['out_win']=list(w)
    local,li=local_plan(P,iW)
    tag=f"r6i_{w[0]}{w[1]}_{w[3]}_{w[4]}"
    log('gate Out Of Control>When My Love',w)
    try:
      f=HERE/f'_bg_{tag}_plan.json';json.dump(local,open(f,'w'))
      t0=time.time();M=BG.dry_meta(str(f),tag);dry_s=time.time()-t0
      r=BG.gate_blend(M,li,GAIN,NUDGE,use_cache=True,keep=False)
      s=summarize(r);s.update(role='candidate',window=list(w),dry_s=round(dry_s,1))
      log('  ->',s)
    except Exception as e:
      s=dict(role='candidate',window=list(w),ok=False,error=f'{type(e).__name__}: {e}'[:400])
      log('  ERROR',s['error']);traceback.print_exc()
    finally:
      try:os.remove(HERE/f'_bg_{tag}_plan.json')
      except FileNotFoundError:pass
    results.append(s)
    if s.get('ok') and pick is None:
      pick=list(w);log('  PICK',w)
  report=dict(note='r6i fix1: later OOC exits, keep WML ib=16; 104 not in pair table',
              candidates=results,pick=pick,ok=pick is not None,
              finished=time.strftime('%Y-%m-%dT%H:%M:%S'))
  json.dump(report,open(OUT_JSON,'w'),indent=1)
  log('wrote',OUT_JSON,'pick',pick)
  sys.exit(0 if pick else 2)

if __name__=='__main__':
  main()
