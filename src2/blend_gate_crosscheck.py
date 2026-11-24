#!/usr/bin/env python3
"""For every blend the gate failed but the old full-render log called clean: run the SAME shared release check on the FULL mix meta
with today's code and features. Agreement = the clean label is stale (features/code changed since that render), not a gate false fail.
Meta-only or deck-render checks only (the old full-mix audio files are gone). Writes eval/blend_gate_crosscheck.json."""
import os,sys,json,subprocess
HERE=os.path.dirname(os.path.abspath(__file__));ROOT=os.path.dirname(HERE)
CHILD=r'''
import sys,json;sys.path[:0]=['../src/tests','../src/build_qa']
import checks as C
out={}
want=set(json.loads(sys.argv[1]))
if want&{'V1','test_no_vocal_clash'}:
  out['vocal']=[[c['a'],c['b'],c.get('t'),c['bars']] for c in C.vocal_clashes() if not c['whitelisted'] and c['bars']>=1]
if 'test_outgoing_audio_tail_never_drops_abruptly' in want:
  import test_release_structure_tail as T
  try:T.test_outgoing_audio_tail_never_drops_abruptly();out['tail']=[]
  except AssertionError as e:out['tail']=eval(str(e).split('\n')[0]) if str(e).startswith('[') else str(e)
  except BaseException as e:out['tail']='not run: '+type(e).__name__+': '+str(e)[:200]  # pytest.skip (stems missing) is a BaseException
print('@@'+json.dumps(out,default=str))
'''
def main(files):
  res=[]
  for f in files:
    V=json.load(open(f))
    for n,m in V['mixes'].items():
      ff=[r for r in m['rows'] if r['false_fail']]
      if not ff:continue
      want=sorted({c for r in ff for c in r['fails']})
      p=subprocess.run([sys.executable,'-c',CHILD,json.dumps(want)],cwd=HERE,capture_output=True,text=True,
        env=dict(os.environ,MIX_SRC=HERE,MIX_NAME=n,NUDGE=os.environ.get('NUDGE','nudge08_r9c.json')))
      js=[l for l in p.stdout.splitlines() if l.startswith('@@')];O=json.loads(js[-1][2:]) if js else dict(error=p.stderr[-300:])
      for r in ff:
        agree={}
        for c in r['fails']:
          if c in('V1','test_no_vocal_clash'):agree[c]=any(a==r['a'] and b==r['b'] or a==r['b'] and b==r['a'] for a,b,*_ in O.get('vocal',[]))
          elif c=='test_outgoing_audio_tail_never_drops_abruptly':agree[c]=(isinstance(O.get('tail'),list) and any(x[0]==r['a'] for x in O['tail'])) if not str(O.get('tail','')).startswith('not run') else None
          else:agree[c]=None
        res.append(dict(note=O.get('tail') if isinstance(O.get('tail'),str) else O.get('error'),mix=n,trans=r['trans'],a=r['a'],b=r['b'],t=r['t'],fails=r['fails'],full_mix_today=agree,stale_label=all(v is True for v in agree.values())))
        print(res[-1],flush=True)
  json.dump(res,open(os.path.join(ROOT,'eval/blend_gate_crosscheck.json'),'w'),indent=1)
  print('stale',sum(r['stale_label'] for r in res),'of',len(res))
if __name__=='__main__':main(sys.argv[1:])
