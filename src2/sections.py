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
def _structure_drop(g):
  """first drop bar from protrans/structure.py's phase labels (drums+bass energy with breakdown detection), or None"""
  import sys
  here=os.path.dirname(os.path.abspath(__file__));p=os.path.join(here,'..','protrans')
  if p not in sys.path:sys.path.insert(0,p)
  import structure as ST
  B=g['bar'];dr=np.asarray(B.get('drums') or B.get('all') or [],float);bs=np.asarray(B.get('bass') or B.get('low') or dr,float)
  n=min(len(dr),len(bs))
  if n<16:return None
  return ST.first_drop_bar(ST.label_phases(dict(drums=dr[:n],bass=bs[:n],n=n)))
RECONCILE_V=3
def reconcile(s,g):
  """drop1 from structure.py when sections' own detector disagrees (2026-11-11 RCA: Dusk To Dawn sections drop1=56, but bars 62-63
  dip and the drop lands at 64, where structure.py puts it; STRUCT then started the incoming 8 bars early). Kept only if it stays
  a valid structure (before outro_start). The detector's value stays in drop1_sections."""
  try:f=_structure_drop(g)
  except Exception as e:s['drop1_note']=f'structure.py failed: {type(e).__name__}';return s
  d0=s.get('drop1')
  if f is None or d0 is None or f==d0 or not 0<=f<s['outro_start']:return s
  # only the RCA shape: structure.py's drop is phrase-aligned and up to one 8-bar phrase LATER (sections fired on a fake start
  # with a dip before the real drop). Earlier/off-phrase/large moves (50/127 tracks on 2026-11-11, mostly +-1..4 bars) are
  # structure.py's own jitter, not a fix; they are recorded in drop1_structure only.
  if f%8 or not 0<f-d0<=8:s=dict(s);s['drop1_structure']=int(f);return s
  s=dict(s);s['drop1_sections']=s.get('drop1_sections',s['drop1']);s['drop1']=int(f);s['drop1_src']='structure.py'
  if s.get('intro_end')==s['drop1_sections']:s['intro_end']=int(f)
  if s.get('drops') and s['drops'][0][0]==s['drop1_sections']:s['drops']=[[int(f),s['drops'][0][1]]]+[list(d) for d in s['drops'][1:]]
  return s
RECONCILE=os.environ.get('SECTIONS_RECONCILE','0')=='1'  # opt-in: held-out 30.09 -> 29.50 with it on (2026-11-11 cohort), so off by default
def get(b,root='.'):
  p=os.path.join(root,'st',f'{b}.sections.json');gp=os.path.join(root,'st',f'{b}.json')
  s=json.load(open(p)) if os.path.exists(p) and os.path.getmtime(p)>=os.path.getmtime(gp) else None
  if s is None or (RECONCILE and s.get('reconcile')!=RECONCILE_V) or (not RECONCILE and 'reconcile' in s):
    g=json.load(open(gp));s=detect(g)
    if RECONCILE:
      s=reconcile(s,g)
      if 'drop1_src' not in s:s['drop1_note']='kept sections drop1 (structure.py agrees, has no valid drop, or is not a phrase-aligned <=8-bar-later drop)'
      s['reconcile']=RECONCILE_V
    tmp=p+f'.tmp{os.getpid()}';json.dump(s,open(tmp,'w'));os.replace(tmp,p)
  return s
if __name__=='__main__':
  ids=sys.argv[1:] or sorted(f[:-5] for f in os.listdir('st') if f.endswith('.json') and f.count('.')==1)
  for b in ids:print(b,get(b))
