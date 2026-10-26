import sys,collections,numpy as np;sys.path.insert(0,'../src/tests');import checks as C
m=C.meta();ref=C.ref_phase();D=collections.defaultdict(list)
for b in range(0,len(C.bar_rms())-4,8):
  p=C.phase_ms(b)
  if p is None: continue
  s=((p-ref+43)%86.2)-43;on=[x['id'] for x in m['decks'] if x['start_bar']<=b<x['end_bar']]
  if len(on)==1: D[on[0]].append(round(s))
  if abs(s)>10: print(b,round(s),on)
for k,v in D.items(): print(k,'median',np.median(v),v)
