import os,sys,json
os.chdir('/workspace/mixes/src2')
os.environ.update(BADW_NEWONLY='1',PAIR_TABLE='pair_table_05v2.json',TABLE_K='400',DROP_FRAC='0.25',BOTHMIN='8')
sys.path.insert(0,'.');import plan_search as P
T=json.load(open('pair_table_05v2.json'));BADW=P.bad_windows();PR=P.prefs()
O=json.load(open('../mix05v2/order_reorder.json'));G=('j9AuFRpLk7U','cxS6yd0UAxw')
def nwin(a,b):
  r=T['pairs'].get(f'{a}>{b}')
  if not r or not r['key_ok']:return 0
  if (a,b)==G:return 1
  return sum(1 for w in r['wins'] if not(w['voc'] or w['both']<P.BOTHMIN or (w['R']<0.2) or w['mel']>P.MELMAX or w['boff']>P.BOFFMAX or w['w'] in BADW.get(f'{a}>{b}',[]) or (w['step']>P.STEPMAX and PR.get(f'{a}>{b}',3)<4)))
cands=set()
def add(o):
  if o[0]!=O[0]:return
  i=o.index(G[0]);
  if i+1<len(o) and o[i+1]==G[1]:cands.add(tuple(o))
n=len(O)
for i in range(1,n):
  for j in range(1,n):
    if abs(i-j)<=4 and i!=j:
      o=O[:];t=o.pop(i);o.insert(j,t);add(o)
    if i<j<=i+4:
      o=O[:];o[i],o[j]=o[j],o[i];add(o)
for d in ['MoYkYkoeb84','5196v8VY1LI','YNz30crm5g0','6YDKymmWe9o','nT25guf4DRU','7Itbo72XEz4']:
  add([x for x in O if x!=d])
res=[]
for o in cands:
  c=[nwin(a,b) for a,b in zip(o,o[1:])]
  if min(c)>0:res.append((min(c),sum(min(x,20) for x in c),list(o)))
res.sort(key=lambda r:(-r[0],-r[1]))
print(len(cands),len(res));json.dump(res,open('../mix05v2/sweep3_cands.json','w'))
for r in res[:20]:print(r[0],r[1],[x[:4] for x in r[2]])
