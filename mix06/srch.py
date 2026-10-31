import sys,json,os,pickle
sys.argv=['x'];os.chdir('/workspace/mixes/src2')
sys.path.insert(0,'/workspace/mixes/src2')
import plan_search as P
lo,hi=float(os.environ.get('LO',60)),float(os.environ.get('HI',66))
ex=tuple(x for x in os.environ.get('EX','').split(',') if x);ban=tuple(x for x in os.environ.get('BAN','').split(',') if x)
done,K,st=P.search('plan_mix06_base.json',lo,hi,int(os.environ.get('BEAM',300)),fix_open=False,exclude=ex,ban=ban)
done.sort(key=lambda d:(len(d['fails']),sum(w['pen'] for w in d['bl'])))
ex05=set(open('../mix06/ex05.txt').read().split(','))
pickle.dump(done[:400],open('../mix06/done.pkl','wb'))
seen=set();n=0
for d in done:
  if tuple(d['seq']) in seen: continue
  seen.add(tuple(d['seq']));n+=1
  print(n,d['fails'],d['pred'],'reuse',sum(b in ex05 for b in d['seq']),round(d['cost'],1))
  if n>=15:break
