#!/usr/bin/env python3
"""r6g: keep r6e order, apply the already-gated Together>In The Night window, and re-gate
Out Of Control>When My Love after n1_grid_align offsets on When My Love's thin intro."""
import copy,json,os,sys,time,traceback
from pathlib import Path

HERE=Path('/workspace/mixes/src2')
sys.path.insert(0,str(HERE))
os.chdir(HERE)
import blend_gate as BG

PLAN_IN=HERE/'plan_mix10_r6e.json'
PLAN_OUT=HERE/'plan_mix10_r6g.json'
OUT_JSON=Path('/workspace/mixes/mix10/gate_r6g_alts_results.json')
GAIN=float(os.environ.get('GAIN','9.0'))
NUDGE=os.environ.get('NUDGE','nudge08_r9c.json')

TOGETHER_WIN=['n',240,None,48,16]  # already passed the audio gate in r6f
TOGETHER=('3f-XOhfDhxk','-n50uo8so4U')
WML=('jIqXQ8EbKNY','7Itbo72XEz4')
# legal ib=16 families (e=64 windows were refused by mix_simple)
WML_CANDS=[['n',128,None,16,16],['la',128,112,16,16],['lb',128,None,16,16],
           ['n',112,None,16,16],['n',80,None,16,16],['n',128,None,16,32]]

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
  mix=sorted({f['check'] for f in r.get('mix_level') or []})
  return dict(ok=r.get('ok'),blend_fails=fails,mix_level=mix,
              secs=(r.get('secs') or {}).get('total'),cached=r.get('cached'),
              window=r.get('window'),a=r.get('a'),b=r.get('b'),
              msgs=[f.get('msg','')[:240] for f in (r.get('blend_fails') or [])][:4])

def main():
  # confirm the sidecar is in place (engine + feat_hash will see it)
  ng=HERE/'st'/'7Itbo72XEz4.nudge.json'
  if not ng.exists():
    sys.exit('missing st/7Itbo72XEz4.nudge.json — run n1_grid_align.py --write first')
  log('When My Love intro offsets', json.load(open(ng)))
  plan=json.load(open(PLAN_IN))
  iT=idx_of(plan,TOGETHER[0],TOGETHER[1])
  plan[iT]['out_win']=list(TOGETHER_WIN)
  iW=idx_of(plan,WML[0],WML[1])
  results=[];pick=None
  for w in WML_CANDS:
    P=copy.deepcopy(plan);P[iW]['out_win']=list(w)
    local,li=local_plan(P,iW)
    tag=f"r6g_{w[0]}{w[1]}_{w[3]}_{w[4]}"
    log('dry+gate Out Of Control>When My Love',w)
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
      pick=list(w);log('  PICK',w);break
  report=dict(together=TOGETHER_WIN,candidates=results,pick=pick,ok=pick is not None,
              started=time.strftime('%Y-%m-%dT%H:%M:%S'))
  if pick is None:
    json.dump(report,open(OUT_JSON,'w'),indent=1,default=str)
    log('NO PASSING WINDOW for Out Of Control>When My Love');sys.exit(2)
  plan[iW]['out_win']=list(pick)
  json.dump(plan,open(PLAN_OUT,'w'),indent=1)
  log('wrote',PLAN_OUT)
  # confirm both changed blends on a full-plan dry
  log('full-plan dry')
  t0=time.time();M=BG.dry_meta(str(PLAN_OUT),'r6g_full');log(f'full dry {time.time()-t0:.1f}s')
  gates=[]
  for a,b,name in [(TOGETHER[0],TOGETHER[1],'Together>In The Night'),(WML[0],WML[1],'Out Of Control>When My Love')]:
    ti=next(k for k,t in enumerate(M['trans']) if t['a']==a and t['b']==b)
    log('full-plan gate',name,'trans',ti)
    r=BG.gate_blend(M,ti,GAIN,NUDGE,use_cache=True,keep=False)
    s=summarize(r);s.update(name=name,role='full_plan_confirm');log('  ->',s);gates.append(s)
  report['confirm']=gates;report['ok']=all(g.get('ok') for g in gates)
  json.dump(report,open(OUT_JSON,'w'),indent=1,default=str)
  log('report',OUT_JSON,'ok',report['ok'])
  sys.exit(0 if report['ok'] else 2)

if __name__=='__main__':
  main()
