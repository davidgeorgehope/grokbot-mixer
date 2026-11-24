#!/usr/bin/env python3
"""If r6h QA fails, identify the blend(s) and run the audio gate on their current windows."""
import json,os,sys,re,traceback,time
from pathlib import Path

HERE=Path('/workspace/mixes/src2')
sys.path.insert(0,str(HERE))
os.chdir(HERE)
import blend_gate as BG

OUT=Path('/workspace/mixes/mix10/gate_r6h_fail_diag.json')
GAIN=float(os.environ.get('GAIN','9.0'))
NUDGE=os.environ.get('NUDGE','nudge08_r9c.json')

def log(*a):
  print(f"[{time.strftime('%H:%M:%S')}]",*a,flush=True)

def load_fails():
  gpath=HERE/'guard_mix10_r6h'/'guardrails.json'
  g=json.load(open(gpath)) if gpath.exists() else {}
  pytest_log=(HERE/'guard_mix10_r6h'/'pytest.log').read_text() if (HERE/'guard_mix10_r6h'/'pytest.log').exists() else ''
  return g, pytest_log

def pairs_from_guard(g, meta):
  """Map guardrail / pytest failures to plan transitions when we can."""
  trans=meta.get('trans') or []
  hits=[]
  for f in g.get('failures') or []:
    msg=str(f)
    # common: ids or t=mm:ss
    ids=re.findall(r'[-\w]{11}', msg)
    t=f.get('t') or f.get('time')
    bar=f.get('bar') or f.get('start_bar')
    hits.append(dict(check=f.get('check'),msg=str(f.get('msg') or msg)[:400],ids=ids,t=t,bar=bar))
  return hits

def idx_near_bar(meta, bar):
  if bar is None: return None
  best=None
  for i,t in enumerate(meta['trans']):
    s,e=t['start_bar'],t['end_bar']
    if s<=bar<e: return i
    d=min(abs(bar-s),abs(bar-e))
    if best is None or d<best[0]: best=(d,i)
  return best[1] if best else None

def summarize(r):
  fails=sorted({f['check'] for f in r.get('blend_fails') or []})
  return dict(ok=r.get('ok'),blend_fails=fails,secs=(r.get('secs') or {}).get('total'),
              cached=r.get('cached'),window=r.get('window'),a=r.get('a'),b=r.get('b'),
              msgs=[f.get('msg','')[:300] for f in (r.get('blend_fails') or [])][:6])

def main():
  meta=json.load(open(HERE/'mix10_r6h_meta.json')) if (HERE/'mix10_r6h_meta.json').exists() else {}
  plan=json.load(open(HERE/'plan_mix10_r6h.json'))
  g,plog=load_fails()
  py=re.findall(r'FAILED .*::(\w+)', plog)
  hits=pairs_from_guard(g, meta)
  # unique transition indices to gate
  idxs=set()
  for h in hits:
    if h.get('bar') is not None:
      i=idx_near_bar(meta,h['bar'])
      if i is not None: idxs.add(i)
    ids=h.get('ids') or []
    if len(ids)>=2 and meta.get('trans'):
      for i,t in enumerate(meta['trans']):
        if t['a'] in ids and t['b'] in ids:
          idxs.add(i)
  # if nothing mapped, gate nothing but still report
  results=[]
  need_search=False
  if idxs:
    # dry the full plan once for meta, then gate those blends
    log('gating failed blends',sorted(idxs))
    try:
      M=BG.dry_meta(str(HERE/'plan_mix10_r6h.json'),'r6hdiag')
    except Exception as e:
      log('dry_meta failed',e); traceback.print_exc()
      M=None
    if M:
      for i in sorted(idxs):
        try:
          r=BG.gate_blend(M,i,GAIN,NUDGE,use_cache=True,keep=False)
          s=summarize(r); s['trans']=i
          log('  ->',s)
          results.append(s)
          if not s.get('ok'): need_search=True
        except Exception as e:
          results.append(dict(trans=i,ok=False,error=f'{type(e).__name__}: {e}'[:400]))
          need_search=True; traceback.print_exc()
  else:
    need_search=True
  report=dict(
    note='r6h post-fail diagnosis (audio gate on implicated blends only; no re-search launched)',
    pytest_fails=py,
    guard_checks=sorted({f.get('check') for f in (g.get('failures') or []) if f.get('check')}),
    guard_hits=hits[:20],
    gated=results,
    may_need_research=need_search,
    finished=time.strftime('%Y-%m-%dT%H:%M:%S'),
  )
  json.dump(report,open(OUT,'w'),indent=1)
  log('wrote',OUT)
  if need_search:
    print('R6H_NEEDS_RESEARCH: one or more blends still fail the gate, or the fail could not be mapped to a single window. Rerun the gated search with the fixed checker rather than loosening thresholds.')
  sys.exit(0)

if __name__=='__main__':
  main()
