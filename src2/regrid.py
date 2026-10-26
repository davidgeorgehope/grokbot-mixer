# Replace beat-tracker downbeats with a robust linear 174-BPM grid (tracks are already rubberband-stretched to exactly 174),
# so breakdown bars aren't sliced on pad/vocal onsets. Backs up st/X.json -> st/X.json.bak once.
import json,sys,os,numpy as np
BAR=4*60/174
for b in sys.argv[1:]:
  f=f'st/{b}.json';g=json.load(open(f))
  if not os.path.exists(f+'.bak'): json.dump(g,open(f+'.bak','w'))
  d=np.array(json.load(open(f+'.bak'))['downs']);k=np.arange(len(d))
  r=d-k*BAR;a=np.median(r)  # fixed slope = exact bar length
  dev=(r-a)*1000;print(b,'resid ms p50/p95/max',np.round(np.percentile(np.abs(dev),[50,95,100]),1),'bars >8ms',int((np.abs(dev)>8).sum()),'/',len(d))
  if '--apply' in sys.argv[0:] and '--dry' not in sys.argv: pass
  g['downs']=(a+k*BAR).tolist()
  if 'phrases' in g:
    q=int(np.argmin(np.abs(d-g['phrases'][0])));g['phrases']=g['downs'][q%8::8]
  if '--dry' not in sys.argv: json.dump(g,open(f,'w'))
