"""Optimise track order for the crossfader engine: shortest path over a transition cost.
cost(a->b) = Camelot cost + energy-step cost + vocal-clash cost (best 16-bar blend window from cached Demucs vocal maps).
First and last tracks stay fixed (opener/closer). usage: python3 order_opt.py plan_in.json plan_out.json"""
import json,sys,os,random,numpy as np
sys.path.insert(0,'../src/tests');os.environ.setdefault('MIX_SRC','.');import checks as C
P=json.load(open(sys.argv[1]));ids=[p['id'] for p in P];K=C.keys();X=16
def kc(a,b):
  na,ma=int(a[:-1]),a[-1];nb,mb=int(b[:-1]),b[-1];d=min((na-nb)%12,(nb-na)%12)
  if ma==mb:return {0:0,1:0.2,2:0.8}.get(d,3.0)
  return {0:0.25,1:0.6}.get(d,3.0)
F={}
for b in ids:
  g=json.load(open(f'st/{b}.json'))['bar'];v=np.array(g['voc'],float);al=np.array(g['all'],float)
  dr=np.array(g.get('drums',g['all']),float);F[b]=dict(vact=v>np.percentile(v,95)-14,energy=float(np.percentile(dr,75)),nb=len(al))
def vclash(a,b):
  A,B=F[a],F[b];best=99
  for e in range(A['nb']-A['nb']%16,A['nb']//2,-16):
    wa=A['vact'][e-X:e]
    for ib in range(0,49,16):
      wb=B['vact'][ib:ib+X]
      if len(wa)<X or len(wb)<X:continue
      k=np.arange(X);x=(k+.5)/X;m=(np.cos(x*np.pi/2)>.3)&(np.sin(x*np.pi/2)>.3)
      best=min(best,int((wa&wb&m).sum()))
  return best
W=dict(key=float(os.environ.get('WKEY',1)),energy=float(os.environ.get('WEN',0.15)),voc=float(os.environ.get('WVOC',0.5)))
cost={(a,b):W['key']*kc(K[a],K[b])+W['energy']*abs(F[b]['energy']-F[a]['energy'])+W['voc']*vclash(a,b) for a in ids for b in ids if a!=b}
def total(o):return sum(cost[(a,b)] for a,b in zip(o,o[1:]))
mid=ids[1:-1];best=(total(ids),ids);random.seed(1)
for r in range(200):
  m=mid[:];random.shuffle(m);o=[ids[0]]+m+[ids[-1]];c=total(o)
  for it in range(3000):
    i,j=sorted(random.sample(range(1,len(o)-1),2));n=o[:i]+o[i:j+1][::-1]+o[j+1:];cn=total(n)
    if cn<=c:o,c=n,cn
  if c<best[0]:best=(c,o)
c,o=best;print('cost before',round(total(ids),2),'after',round(c,2))
for a,b in zip(o,o[1:]):print(K[a],'->',K[b],a,'->',b,'key',kc(K[a],K[b]),'voc',vclash(a,b))
step={p['id']:p for p in P};out=[dict(step[b]) for b in o];out[0]['tech']='first'
for s in out[1:]:s['tech']='blend' if s['tech']=='first' else s['tech']
json.dump(out,open(sys.argv[2],'w'),indent=1)
