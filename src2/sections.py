"""DnB song structure per track from the bar features in st/<id>.json (bar-level dB of all/low/drums) on the 8/16-bar phrase grid:
intro (0..drop1), drop1, breakdown, drop2, outro_start, music_end. Stored in st/<id>.sections.json.
A 'drop' = >=8 bars where the low band sits within 6 dB of the track's loud-low level (the 80th percentile) and drums play."""
import json,os,sys,numpy as np
def _runs(mask,minlen=8):
  r=[];k=0;n=len(mask)
  while k<n:
    if mask[k]:
      j=k
      while j<n and mask[j]:j+=1
      if j-k>=minlen:r.append([k,j])
      k=j
    else:k+=1
  # merge runs separated by < 4 bars (fills / one-bar breaks)
  m=[]
  for a,b in r:
    if m and a-m[-1][1]<4:m[-1][1]=b
    else:m.append([a,b])
  return m
def snap(x,q=8):return int(round(x/q)*q)
def detect(g):
  B=g['bar'];al=np.array(B['all'],float);lo=np.array(B['low'],float);dr=np.array(B.get('drums',B['all']),float);n=len(al)
  loud=np.percentile(lo,80);dloud=np.percentile(dr,80)
  m=(lo>loud-6)&(dr>dloud-10)
  m=np.convolve(m.astype(float),np.ones(3)/3,'same')>0.5
  R=_runs(m)
  live=np.where(al>np.max(al)-25)[0];end=int(live[-1])+1 if len(live) else n
  if not R:return dict(n_bars=n,intro_end=0,drop1=0,breakdown=None,drop2=None,outro_start=snap(max(0,end-32)),music_end=end,drops=[])
  S=[]
  for a,b in ([snap(a),snap(b)] for a,b in R):
    if S and a-S[-1][1]<=8:S[-1][1]=max(S[-1][1],b)  # fills / short dips inside a drop
    else:S.append([a,b])
  R=S;d1=R[0][0];d2=R[1][0] if len(R)>1 else None;bd=R[0][1] if len(R)>1 else None
  outro=min(R[-1][1],end);outro=max(min(outro,(end//8)*8-16),d1+16)  # the outgoing always rides >=16 bars of outro
  return dict(n_bars=n,intro_end=d1,drop1=d1,breakdown=bd,drop2=d2,outro_start=int(outro),music_end=int(end),drops=R)
def get(b,root='.'):
  p=os.path.join(root,'st',f'{b}.sections.json');g=os.path.join(root,'st',f'{b}.json')
  if os.path.exists(p) and os.path.getmtime(p)>=os.path.getmtime(g):return json.load(open(p))
  s=detect(json.load(open(g)));json.dump(s,open(p,'w'));return s
if __name__=='__main__':
  ids=sys.argv[1:] or sorted(f[:-5] for f in os.listdir('st') if f.endswith('.json') and f.count('.')==1)
  for b in ids:print(b,get(b))
