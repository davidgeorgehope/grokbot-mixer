#!/usr/bin/env python3
"""Deterministic auto-fix for guardrail timing failures (F1 flam, N1 entry off-grid, G1 grid):
for every flagged transition (or G1 bar), render each deck alone, measure its own 16th-grid phase per bar, and write
warp nudges (ms) for the source bars that sit > 5 ms off the mix grid. usage: autofix.py NAME NUDGE_JSON"""
import os,sys,json
NAME,NF=sys.argv[1],sys.argv[2];SRC='/workspace/mixes/src2';os.environ['NUDGE']=NF;os.environ['MIX_SRC']=SRC;os.environ['MIX_NAME']=NAME
sys.path.insert(0,'/workspace/mixes/src/tests');import deckpair as P,numpy as np
G=json.load(open(f'{SRC}/guard_{NAME}/guardrails.json'));M=P.meta();D=M['decks'];TR=M['trans'];BAR=P.BAR;S16=60/174/4
N=json.load(open(f'{SRC}/{NF}')) if os.path.exists(f'{SRC}/{NF}') else {}
fails=G.get('failures') or G.get('fails') or []
tis=[int(x) for x in os.environ['TRANS'].split(',')] if os.environ.get('TRANS') else sorted({f['trans'] for f in fails if f['check'] in('F1','N1') and 'trans' in f})
changed=0;PH={}
for ti in tis:
  t=TR[ti];ia=max(i for i,d in enumerate(D) if d['id']==t['a'] and d['start_bar']<t['start_bar']+1 and not d['acap'])
  ib=[i for i,d in enumerate(D) if d['id']==t['b'] and abs(d['start_bar']-t['start_bar'])<1e-6][0]
  for i in (ia,ib):
    d=D[i];y=P._render(d)
    for bar in range(int(t['start_bar']),int(min(d['end_bar'],t['end_bar']))):
      if bar<d['start_bar']:continue
      k,st=d['full_map'][int(bar-d['start_bar'])];j=int(round((bar-d['start_bar'])*BAR*P.SR));seg=y[j:j+int(BAR*P.SR)]
      if np.sqrt(np.mean(seg**2))<1e-3:continue
      ph=P.beat_phase(P.snare_env(seg),per=S16)
      if ph is not None:PH.setdefault((d['id'],k),[]).append(ph)

# G1: measure active decks at each flagged 2-bar window
g1_bars=sorted({int(f['sec']/BAR) for f in fails if f['check']=='G1' and 'sec' in f})
for bar in g1_bars:
  for i,d in enumerate(D):
    if d.get('acap'): continue
    if not (d['start_bar']<=bar<d['end_bar']): continue
    y=P._render(d)
    for b in (bar, bar+1):
      if b<d['start_bar'] or b>=d['end_bar']: continue
      idx=int(b-d['start_bar'])
      if idx>=len(d['full_map']): continue
      k,st=d['full_map'][idx]
      j=int(round((b-d['start_bar'])*BAR*P.SR));seg=y[j:j+int(BAR*P.SR)]
      if np.sqrt(np.mean(seg**2))<1e-3:continue
      ph=P.beat_phase(P.snare_env(seg),per=S16)
      if ph is not None:PH.setdefault((d['id'],k),[]).append(ph)

for (did,k),v in PH.items():
  ph=float(np.median(v))
  if abs(ph)>float(os.environ.get('PH_TH',5)):
    cur=N.setdefault(did,{}).get(str(k),0);N[did][str(k)]=int(round(cur-ph));changed+=1
    print(f"nudge {did} src bar {k} {cur} -> {N[did][str(k)]} ms (median phase {ph:+.0f} over {len(v)} plays)")
json.dump(N,open(f'{SRC}/{NF}','w'),indent=1);print('changed',changed)
