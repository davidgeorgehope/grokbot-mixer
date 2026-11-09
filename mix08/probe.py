import os,sys,json,collections
os.chdir('/workspace/mixes/src2');sys.path.insert(0,'.')
import plan_search as P
done,K,st=P.search('plan_mix08_base.json',40,100,400,BW=(200,800),fix_open=False)
h=collections.Counter();best={}
for d in done:
  L=d['pred']['len_min'];h[int(L//2*2)]+=1
  k=int(L//2*2);f=tuple(d['fails'])
  if k not in best or len(f)<len(best[k][0]):best[k]=(f,len(d['seq']),d['pred'])
for k in sorted(h):print(k,h[k],best[k])
ok=[d for d in done if not d['fails']]
for d in sorted(ok,key=lambda d:-d['pred']['len_min'])[:5]:print(d['pred'],d['seq'])
