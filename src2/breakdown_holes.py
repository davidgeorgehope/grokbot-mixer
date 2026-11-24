#!/usr/bin/env python3
"""Breakdown-hole marking (RCA 2026-11-24 fix 2): a track's own deep mid-track breakdown left playing SOLO is a mix-level
energy hole no blend window can fix (Mix 10 r5 Hayling 14:24 E1, r6 Memory Lane 38:38 E4). Precompute per track from the
cached per-bar features (st/<id>.json bar.all) and check a plan meta for solo exposure, so the planner can veto it in seconds.

Rules mirror the render guardrails they predict (thresholds read from the same numbers, nothing loosened):
  E1-deep : source bar <= body-16 dB (guardrails.intentional() only excuses an own breakdown above body-16) and its ~3 s level
            (2-bar power mean) > E1_db=6 under the local ~30 s median (+-11 bars), before the track's own tail.
  (An E4-style 'long lull' mask, > 8 bars > 6 dB under the track body, was tried and dropped: on the Mix 10 r6c render it marked
   14 solo stretches and the real E4 fired on none. The dry check's level-model E4 already covers whole-mix lulls.)
A bar is exposed when its deck is the only one with crossfader gain > SOLO_G at that mix bar.
usage: python3 breakdown_holes.py META.json  -> prints exposures (exit 1 if any)"""
import os,sys,json,functools,numpy as np
HERE=os.path.dirname(os.path.abspath(__file__))
E1_DB,E4_DB,E4_BARS,OWN_DB,LOCAL,SOLO_G=6.0,6.0,8,16.0,11,0.1

@functools.lru_cache(None)
def levels(tid,src=HERE):
  g=json.load(open(os.path.join(src,'st',f'{tid}.json')));return np.array(g['bar']['all'],float)
def track_mask(al):
  """al: per-bar dB of one track -> dict(body, tail0, deep=set(bars), lull=set(bars))"""
  al=np.asarray(al,float);body=float(np.percentile(al,75));loud=np.where(al>body-20)[0]
  head=int(loud[0]) if len(loud) else 0;tail0=int(loud[-1])+1 if len(loud) else len(al)
  p=10**(al/10);s3=10*np.log10(np.convolve(p,[0.5,0.5],'same')+1e-12)
  deep=set()
  for k in range(head,tail0):
    med=float(np.median(al[max(0,k-LOCAL):k+LOCAL+1]))
    if al[k]<=body-OWN_DB and s3[k]<med-E1_DB:deep.add(k)
  low=[head<=k<tail0 and al[k]<body-E4_DB for k in range(len(al))];lull=set();k=0
  while k<len(al):
    if low[k]:
      j=k
      while j<len(al) and low[j]:j+=1
      if j-k>E4_BARS:lull|=set(range(k,j))
      k=j
    else:k+=1
  return dict(body=body,head=head,tail0=tail0,deep=deep,lull=lull)
def _gain(d,bar):
  pts=(d.get('auto') or {}).get('gain')
  if not pts:return 1.0
  return float(np.interp(bar,[p[0] for p in pts],[p[1] for p in pts]))
def exposures(M,src=HERE,levels_of=None):
  """[('E1-deep', deck id, mix bar start, n bars, src bars)] for runs of >= 2 solo bars in the track's E1-deep mask"""
  lv=levels_of or (lambda t:levels(t,src));D=[d for d in M['decks'] if not d.get('acap')];out=[]
  for d in D:
    mk=track_mask(lv(d['id']));run={'E1-deep':[]}
    def flush(kind):
      r=run[kind]
      if len(r)>=2:out.append((kind,d['id'],r[0][0],len(r),[x[1] for x in r]))
      run[kind]=[]
    for j,(sb,stem) in enumerate(d['full_map']):
      b=d['start_bar']+j+0.5;solo=_gain(d,b)>0.5 and all(_gain(e,b)<=SOLO_G for e in D if e is not d and e['start_bar']<=b<e['end_bar'])
      for kind,S in (('E1-deep',mk['deep']),):
        if solo and stem=='mix' and sb in S:run[kind].append((int(b),sb))
        else:flush(kind)
    flush('E1-deep')
  return out
if __name__=='__main__':
  M=json.load(open(sys.argv[1]));X=exposures(M);bs=M['bar_sec']
  for k,t,b,n,sb in X:print(f"{k} {t} at {int(b*bs//60)}:{int(b*bs%60):02d} ({n} solo bars, src {sb[0]}-{sb[-1]})")
  print('exposures',len(X));sys.exit(1 if X else 0)
