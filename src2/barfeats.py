"""Per-bar dB features -> st/<id>.json["bar"]: all, low (<150 Hz), hat (6-16 kHz), voc + drums (from temporary demucs stems).
usage: BF='st/<id>.json' python3 barfeats.py   (default: every st/*.json)"""
import numpy as np,json,glob,os,soundfile as sf
from scipy.signal import butter,sosfilt
SR=44100;SEP=os.environ.get('SEP','sep/htdemucs')
def bandE(y,lo,hi):
  sos=butter(4,[lo,hi],'band',fs=SR,output='sos') if lo>0 else butter(4,hi,'low',fs=SR,output='sos')
  return sosfilt(sos,y)**2
for f in sorted(glob.glob(os.environ.get('BF','st/*.json'))):
  b=os.path.basename(f)[:-5]
  if not os.path.exists(f'st/{b}.wav'):continue
  g=json.load(open(f));y,_=sf.read(f'st/{b}.wav');m=y.mean(1)
  downs=np.array(g['downs']);bar=4*60/174
  E=dict(all=m**2,low=bandE(m,0,150),hat=bandE(m,6000,16000))
  vp=f'{SEP}/{b}/vocals.wav'   # demucs stems are temporary: add_track.sh deletes them after this runs
  if os.path.exists(vp):
    v,_=sf.read(vp);E['voc']=v.mean(1)**2
    d,_=sf.read(f'{SEP}/{b}/drums.wav');E['drums']=d.mean(1)**2
  feats={k:[] for k in E}
  for d0 in downs:
    i0=int(d0*SR);i1=int((d0+bar)*SR)
    for k in E:feats[k].append(float(10*np.log10(E[k][i0:i1].mean()+1e-10)) if i1<=len(m) else -100)
  old=g.get('bar',{});g['bar']={k:np.round(v,2).tolist() for k,v in feats.items()}
  for k in ('voc','drums'):  # no stems now: keep the cached vocal/drum features
    if k not in g['bar'] and k in old:g['bar'][k]=old[k]
  json.dump(g,open(f,'w'))
  lo=np.array(feats['low']);ref=np.percentile(lo,90);bass=lo>ref-8
  print(b,'bars',len(downs),'bass:',''.join('#' if x else '.' for x in bass),flush=True)
