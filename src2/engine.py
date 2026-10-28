"""Core for the crossfader engine (mix_simple.py): track loading, warp nudges, and rendering one deck.
A deck is a list of source bars (full_map) plus one 'gain' curve that comes only from the crossfader.
The only EQ is an optional bass-handoff lane d['auto']['low'] (0..1 on the <XO Hz band, zero-phase split so
low+rest == original exactly): one smooth monotonic swap per blend. No stems, ducking or other filters."""
import numpy as np,soundfile as sf,json,os,pyloudnorm as pyln
from scipy.signal import butter,sosfiltfilt
XO=float(os.environ.get('BASS_XO',150))
SR=44100;T=174.0;BEAT=60/T;BAR=4*BEAT;BS=BAR*SR
_cache={}
class LazySt(dict):
  """'mix' audio loaded on first access, loudness-normalised to -16 LUFS (constant per-track gain); {} frees it."""
  def __init__(s,b):super().__init__();s.b=b
  def __getitem__(s,k):
    if not dict.__contains__(s,'mix'):
      y,_=sf.read(f'st/{s.b}.wav',dtype='float32',always_2d=True)
      dict.__setitem__(s,'mix',y*10**((-16-pyln.Meter(SR).integrated_loudness(y))/20))
    return dict.__getitem__(s,k)
def track(b):
  if b in _cache:return _cache[b]
  g=json.load(open(f'st/{b}.json'));voc=np.array(g['bar'].get('voc',[-100]*len(g['bar']['all'])))
  info=dict(id=b,g=g,st=LazySt(b),d0=g['downs'][0],nb=len(g['downs']),vact=voc>np.percentile(voc,95)-14)
  _cache[b]=info;return info
_NF=os.environ.get('NUDGE','nudge.json');NUDGE=json.load(open(_NF)) if os.path.exists(_NF) else {}  # per-source-bar warp nudges (ms)
def nudge(tr,k):return NUDGE.get(tr['id'],{}).get(str(k),0)
SEAM=int(round(BEAT*SR))
def render_deck(d):
  """Render deck d (meta dict) alone: source bars from full_map, 1-beat linear overlap-add at loop seams,
  times the crossfader gain curve d['auto']['gain'] ([[mix_bar, gain], ...])."""
  tr=track(d['id']);m=[s for s,_ in d['full_map']];n=int(round(len(m)*BS));y=np.zeros((n+SEAM*2,2),np.float32)
  x=tr['st']['mix']
  for k,sb in enumerate(m):
    i0=int(round(k*BS));L=int(round((k+1)*BS))-i0
    j0=int(round((tr['d0']+sb*BAR-nudge(tr,sb)/1000)*SR))
    cont_prev=k>0 and sb==m[k-1]+1 and nudge(tr,sb)==nudge(tr,m[k-1])
    cont_next=k<len(m)-1 and m[k+1]==sb+1 and nudge(tr,m[k+1])==nudge(tr,sb)
    pre=0 if cont_prev or k==0 else SEAM//2;post=0 if cont_next or k==len(m)-1 else SEAM//2
    a0=j0-pre;seg=x[max(0,a0):j0+L+post]
    if a0<0:seg=np.pad(seg,((-a0,0),(0,0)))
    seg=np.pad(seg,((0,max(0,pre+L+post-len(seg))),(0,0)))[:pre+L+post].copy()
    if pre:seg[:2*pre]*=np.linspace(0,1,2*pre,dtype=np.float32)[:,None]  # linear overlap-add seam (correlated material)
    if post:seg[-2*post:]*=np.linspace(1,0,2*post,dtype=np.float32)[:,None]
    o=SEAM+i0-pre;y[o:o+len(seg)]+=seg
  y=y[SEAM:SEAM+n]
  lp=d['auto'].get('low') or []
  if lp:
    t=np.arange(n)/BS+d['start_bar'];gl=np.interp(t,[p[0] for p in lp],[p[1] for p in lp]).astype(np.float32)
    nz=np.where(gl<0.9999)[0]
    if len(nz):
      a0,a1=max(0,nz[0]-SR),min(n,nz[-1]+SR);seg=y[a0:a1]
      low=sosfiltfilt(butter(4,XO,'low',fs=SR,output='sos'),seg,axis=0).astype(np.float32)
      y[a0:a1]=seg-low*(1-gl[a0:a1,None])
  pts=d['auto'].get('gain') or []
  if pts:
    t=np.arange(n)/BS+d['start_bar'];g=np.interp(t,[p[0] for p in pts],[p[1] for p in pts]).astype(np.float32);y*=g[:,None]
  return y
