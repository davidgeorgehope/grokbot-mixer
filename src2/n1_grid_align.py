"""Align a stretch whose N1-style beat phase is consistently off a drop-locked grid, without moving the body.

prep.grid() fits one phase for the whole track. When My Love (7Itbo72XEz4) is the case that
forced this: the drop sits within ~5 ms of that grid, but bars 15-24 (thin intro, first
audible drums) sit 19 ms early — the same “enters -19 ms off the grid” N1 fail seen when the
track is cued at ib=16. FINE_PHASE cannot fix it: it folds on a 43 ms (1/8-beat) template and
would over-correct the intro to +43 ms, and it would also move later drop bars.

This module uses the same metric as guardrails N1 (deckpair.snare_env + beat_phase on the 16th
grid, 2-bar windows) and writes per-bar offsets to st/<id>.nudge.json. engine.nudge() applies
them (positive = read the source earlier so early hits land later on the mix grid). N1_ms=10
and every other threshold stay unchanged.
"""
import json,os,sys
import numpy as np
import soundfile as sf

HERE=os.path.dirname(os.path.abspath(__file__))
SR=44100;T=174.0;BEAT=60/T;BAR=4*BEAT;S16=BEAT/4
# match guardrails N1_ms: only move a stretch that would itself fail the 10 ms entry check
MIN_MS=float(os.environ.get('N1_ALIGN_MIN_MS',10))
MIN_BARS=int(os.environ.get('N1_ALIGN_MIN_BARS',4))
MAX_SPREAD=float(os.environ.get('N1_ALIGN_MAX_SPREAD',8))  # ms; a run must be consistent
BODY_LV=-20.0  # dBFS; drop-level bars define “the grid is already fine here”

def _deckpair():
  tests=os.path.join(HERE,'../src/tests')
  if tests not in sys.path:sys.path.insert(0,tests)
  import deckpair as P;return P

def bar_rows(tid,g=None,bars=None,src=None):
  """[{bar,p16,lv}] using the N1 metric on the track's own audio, placed on its stored downs."""
  src=src or HERE
  g=g or json.load(open(os.path.join(src,'st',f'{tid}.json')))
  downs=np.array(g['downs']);P=_deckpair()
  if bars is None:bars=range(max(0,len(downs)-2))
  rows=[];path=os.path.join(src,'st',f'{tid}.wav')
  with sf.SoundFile(path) as f:
    sr=f.samplerate
    for k in bars:
      if k+2>len(downs):break
      a=max(0,int(round(downs[k]*sr)));n=int(round(2*BAR*sr))
      f.seek(a);seg=f.read(n,dtype='float32',always_2d=True).mean(1)
      if len(seg)<n*0.9:
        rows.append(dict(bar=int(k),p16=None,lv=-120.0));continue
      lv=float(20*np.log10(np.sqrt(np.mean(seg[:int(BAR*sr)]**2))+1e-12))
      p=P.beat_phase(P.snare_env(seg),per=S16,nb=2)
      rows.append(dict(bar=int(k),p16=None if p is None else float(p),lv=lv))
  return rows

def _runs(rows,min_ms=MIN_MS,min_bars=MIN_BARS,max_spread=MAX_SPREAD,body_lv=BODY_LV):
  """contiguous stretches whose N1 phase is consistently off, excluding already-on-grid body bars."""
  # do not move loud body bars that already pass N1 — that is the drop-locked grid
  body=[r['p16'] for r in rows if r['p16'] is not None and r['lv']>=body_lv and abs(r['p16'])<min_ms]
  off=[]
  cur=[]
  def flush():
    if len(cur)<min_bars:cur.clear();return
    xs=[r['p16'] for r in cur]
    if (max(xs)-min(xs))>max_spread:cur.clear();return
    med=float(np.median(xs))
    if abs(med)<min_ms:cur.clear();return
    off.append((list(cur),med));cur.clear()
  for r in rows:
    if r['p16'] is None or r['lv']>=body_lv and abs(r['p16'])<min_ms:
      flush();continue
    if r['p16'] is None or abs(r['p16'])<min_ms:
      flush();continue
    if cur and (r['bar']!=cur[-1]['bar']+1 or (max(r['p16'],max(x['p16'] for x in cur))-min(r['p16'],min(x['p16'] for x in cur)))>max_spread):
      flush()
    cur.append(r)
  flush();return off,body

def nudges_for(tid,g=None,src=None,**kw):
  """{bar: nudge_ms}. Sign matches engine._bars: positive delays early hits onto the mix grid."""
  rows=bar_rows(tid,g=g,src=src)
  runs,_=_runs(rows,**{k:v for k,v in kw.items() if k in('min_ms','min_bars','max_spread','body_lv')})
  out={}
  for cur,med in runs:
    ms=float(round(-med,1))  # p16=-19 (early) -> nudge +19
    if ms==0:continue
    for r in cur:out[int(r['bar'])]=ms
  return out

def write(tid,nudges=None,src=None):
  src=src or HERE
  nudges=nudges if nudges is not None else nudges_for(tid,src=src)
  path=os.path.join(src,'st',f'{tid}.nudge.json')
  payload={str(k):v for k,v in sorted(nudges.items())}
  json.dump(payload,open(path,'w'),indent=1,sort_keys=True)
  return path,payload

def load(tid,src=None):
  p=os.path.join(src or HERE,'st',f'{tid}.nudge.json')
  if not os.path.exists(p):return {}
  d=json.load(open(p));return {int(k):float(v) for k,v in d.items() if str(k).lstrip('-').isdigit()}

def bar_rows_nudged(tid,nudges,g=None,bars=None,src=None):
  """Re-measure N1 phase after applying per-bar nudges (seek to downs[k]-nudge/1000)."""
  src=src or HERE
  g=g or json.load(open(os.path.join(src,'st',f'{tid}.json')))
  downs=np.array(g['downs']);P=_deckpair()
  if bars is None:bars=sorted(nudges)
  rows=[];path=os.path.join(src,'st',f'{tid}.wav')
  with sf.SoundFile(path) as f:
    sr=f.samplerate
    for k in bars:
      if k+2>len(downs):break
      t0=downs[k]-float(nudges.get(k,0))/1000.0
      a=max(0,int(round(t0*sr)));n=int(round(2*BAR*sr))
      f.seek(a);seg=f.read(n,dtype='float32',always_2d=True).mean(1)
      if len(seg)<n*0.9:
        rows.append(dict(bar=int(k),p16=None,lv=-120.0));continue
      lv=float(20*np.log10(np.sqrt(np.mean(seg[:int(BAR*sr)]**2))+1e-12))
      p=P.beat_phase(P.snare_env(seg),per=S16,nb=2)
      rows.append(dict(bar=int(k),p16=None if p is None else float(p),lv=lv))
  return rows

if __name__=='__main__':
  ids=sys.argv[1:] or ['7Itbo72XEz4']
  do_write='--write' in ids;ids=[x for x in ids if not x.startswith('-')]
  os.chdir(HERE)
  for tid in ids:
    n=nudges_for(tid)
    print(tid,'nudges',n)
    if do_write:
      p,d=write(tid,n);print('wrote',p,d)
