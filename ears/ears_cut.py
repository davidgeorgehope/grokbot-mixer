"""Box side (light): cut each blend of a render meta into two ungained per-deck clips + per-bar gains.
Usage: python ears_cut.py META.json OUTDIR [--nudge nudgeX.json] [--pad 0]
Runs from src2/ paths (st/<id>.wav, st/<id>.json). Writes OUTDIR/tNN_{A,B}.flac (mono 44.1k) and OUTDIR/blends.json."""
import sys,os,json,argparse,numpy as np,soundfile as sf
ap=argparse.ArgumentParser();ap.add_argument('meta');ap.add_argument('out');ap.add_argument('--nudge',default='');ap.add_argument('--src',default=os.path.join(os.path.dirname(__file__),'..','src2'))
a=ap.parse_args();os.makedirs(a.out,exist_ok=True)
M=json.load(open(a.meta));SR=44100;BAR=M['bar_sec'];NU=json.load(open(a.nudge)) if a.nudge else {}
def deck(i):return next(d for d in M['decks'] if d['id']==i)
def gain(d,t):p=d['auto'].get('gain') or [];return float(np.interp(t,[x[0] for x in p],[x[1] for x in p])) if p else 1.0
def clip(d,b0,b1):
  g=json.load(open(f"{a.src}/st/{d['id']}.json"));d0=g['downs'][0];m=[s for s,_ in d['full_map']]
  info=sf.info(f"{a.src}/st/{d['id']}.wav");out=[]
  with sf.SoundFile(f"{a.src}/st/{d['id']}.wav") as f:
    for b in range(b0,b1):
      sb=m[b-d['start_bar']];nu=NU.get(d['id'],{}).get(str(sb),0)/1000
      j0=int(round((d0+sb*BAR-nu)*SR));L=int(round((b+1-b0)*BAR*SR))-int(round((b-b0)*BAR*SR))
      f.seek(max(0,min(j0,info.frames-1)));x=f.read(L,dtype='float32',always_2d=True).mean(1)
      out.append(np.pad(x,(0,L-len(x))))
  return np.concatenate(out)
rows=[]
for k,t in enumerate(M['trans']):
  A,B=deck(t['a']),deck(t['b']);b0,b1=int(t['start_bar']),int(t['end_bar'])
  for tag,d in (('A',A),('B',B)):sf.write(f"{a.out}/t{k:02d}_{tag}.flac",clip(d,b0,b1),SR)
  rows.append(dict(k=k,a=t['a'],b=t['b'],start_bar=b0,end_bar=b1,t0=b0*BAR,
    ga=[gain(A,b+.5) for b in range(b0,b1)],gb=[gain(B,b+.5) for b in range(b0,b1)],notes=t.get('notes',[])))
json.dump(dict(meta=os.path.basename(a.meta),bar_sec=BAR,blends=rows),open(f"{a.out}/blends.json",'w'),indent=1)
print(len(rows),'blends ->',a.out)
