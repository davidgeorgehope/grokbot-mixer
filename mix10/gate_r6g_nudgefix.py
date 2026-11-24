#!/usr/bin/env python3
"""Re-gate Out Of Control -> When My Love after checks.nudge_ms learned the sidecar.
Does not write a new mix plan or start a render/search."""
import copy,json,os,sys,time,traceback
from pathlib import Path

HERE=Path('/workspace/mixes/src2')
sys.path.insert(0,str(HERE))
os.chdir(HERE)
import blend_gate as BG

PLAN_IN=HERE/'plan_mix10_r6e.json'
OUT_JSON=Path('/workspace/mixes/mix10/gate_r6g_nudgefix_results.json')
GAIN=float(os.environ.get('GAIN','9.0'))
NUDGE=os.environ.get('NUDGE','nudge08_r9c.json')
TOGETHER_WIN=['n',240,None,48,16]
WML=('jIqXQ8EbKNY','7Itbo72XEz4')
# legal ib=16 families; skip the 32-bar window (already a V1 vocal clash, independent of nudge)
WML_CANDS=[['n',128,None,16,16],['la',128,112,16,16],['n',112,None,16,16],['n',80,None,16,16]]

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
  # apply the already-passing Together window so the local 4-track clip matches r6g
  ids=[p['id'] for p in plan]
  for i in range(len(ids)-1):
    if ids[i]=='3f-XOhfDhxk' and ids[i+1]=='-n50uo8so4U':
      plan[i]['out_win']=list(TOGETHER_WIN)
  iW=idx_of(plan,WML[0],WML[1])
  results=[];pick=None
  for w in WML_CANDS:
    P=copy.deepcopy(plan);P[iW]['out_win']=list(w)
    local,li=local_plan(P,iW)
    tag=f"r6gfix_{w[0]}{w[1]}_{w[3]}_{w[4]}"
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
      # keep going so we know how many legal windows now pass
  report=dict(note='re-gate after checks.nudge_ms applies st/<id>.nudge.json',
              candidates=results,pick=pick,ok=pick is not None,
              finished=time.strftime('%Y-%m-%dT%H:%M:%S'))
  json.dump(report,open(OUT_JSON,'w'),indent=1)
  log('wrote',OUT_JSON,'pick',pick)
  sys.exit(0 if pick else 2)

if __name__=='__main__':
  main()
