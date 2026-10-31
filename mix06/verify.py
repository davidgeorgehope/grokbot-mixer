import sys,json,os,pickle
sys.path.insert(0,'/workspace/mixes/src2');sys.argv=['x'];os.chdir('/workspace/mixes/src2')
import plan_search as P
done=pickle.load(open('../mix06/done.pkl','rb'));seen=set();n=0
ex05=set(open('../mix06/ex05.txt').read().split(','))
cands=[d for d in done if not d['fails']]
cands.sort(key=lambda d:(sum(b in ex05 for b in d['seq']),d['cost']))
for d in cands:
  if tuple(d['seq']) in seen:continue
  seen.add(tuple(d['seq']));n+=1
  Pl=P.to_plan(d,'plan_mix06_base.json');v=P.dry(Pl,100+n)
  print(n,'reuse',sum(b in ex05 for b in d['seq']),v.get('tests'),v.get('E4'),v.get('len_min'),flush=True)
  if v.get('all_ok'):
    out=os.environ.get('OUT','plan_mix06a.json');json.dump(Pl,open(out,'w'),indent=1);print('SAVED',out,d['seq']);break
  if n>=int(os.environ.get('NV',12)):break
