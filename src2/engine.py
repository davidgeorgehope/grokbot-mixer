"""Core for the crossfader engine (mix_simple.py): track loading, warp nudges, and rendering one deck.
A deck is a list of source bars (full_map) plus one 'gain' curve that comes only from the crossfader.
The only EQ is an optional bass-handoff lane d['auto']['low'] (0..1 on the <XO Hz band, zero-phase split so
low+rest == original exactly): one smooth monotonic swap per blend; plus, with HIGH_SWAP, the same kind of lane
d['auto']['high'] on the >HIGH_XO Hz band; plus the optional delay-tail exit d['echo_out'] (echo_tail). No ducking or other filters; the only stem use is the beat-only (drums+bass) source of a synthetic outro ('lx'), switched in before the blend."""
import numpy as np,soundfile as sf,json,os,pyloudnorm as pyln
from scipy.signal import butter,sosfiltfilt
XO=float(os.environ.get('BASS_XO',150));HXO=float(os.environ.get('HIGH_XO',2000))
SR=44100;T=174.0;BEAT=60/T;BAR=4*BEAT;BS=BAR*SR
_cache={}
class LazySt(dict):
  """'mix' audio loaded on first access, loudness-normalised to -16 LUFS (constant per-track gain); {} frees it."""
  def __init__(s,b):super().__init__();s.b=b
  def __getitem__(s,k):
    if not dict.__contains__(s,'mix'):
      y,_=sf.read(f'st/{s.b}.wav',dtype='float32',always_2d=True);g=10**((-16-pyln.Meter(SR).integrated_loudness(y))/20)
      dict.__setitem__(s,'gain',g);dict.__setitem__(s,'mix',y*g)
    if k=='beat' and not dict.__contains__(s,'beat'):  # drums+bass stem (beatstem.py), same per-track gain as 'mix' so the stems sum back to it
      import beatstem;y,_=sf.read(beatstem.ensure(s.b),dtype='float32',always_2d=True);dict.__setitem__(s,'beat',y*s['gain'])
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
  tr=track(d['id']);m=[s for s,_ in d['full_map']];n=int(round(len(m)*BS))
  src=[c for _,c in d['full_map']];y=_bars(tr,m,tr['st']['mix'],n)
  if 'beat' in src:  # synthetic beat-only outro ('lx'): the same bar map from the drums+bass stem, faded in over LX_XF bars that END
    k0=src.index('beat');xf=int(d.get('lx_xf',2))  # where the beat-only bars start (before the blend; the stems are phase-identical to the mix)
    yb=_bars(tr,m,tr['st']['beat'],n)
    # LX_PHASE (2026-11-01, Mix 05 v2 i18/r0 G1 x4-5, F1 x2): the beat-only loop jumps ~30 source bars back (e.g. bar 159 -> 130);
    # the track's own grid drifts 8-16 ms over that span, so the loop landed off the beat. Re-phase the loop bars to the music before the switch.
    if int(os.environ.get('LX_PHASE',1)) and k0>=2:
      sh=_lx_shift(y,yb,k0)
      if sh:yb=_bars(tr,m,tr['st']['beat'],n,extra={k:sh for k,c in enumerate(src) if c=='beat'})
    # LX_TRIM (2026-11-01, Mix 05 v2 r0 N1 +9.9 dB at 45:25 AC3e>n1dO): the drums+bass stem sits ~6-7 dB under the full mix it replaces,
    # so the beat-only bars left a dip and the blend entry read as a level step. One static source trim on the stem (channel gain, not a
    # per-bar ride; the crossfader stays one monotonic curve per deck): match the stem to the mix bars before the switch, LX_TRIM_DB under, cap +9 dB.
    if int(os.environ.get('LX_TRIM',1)) and k0>=4:
      i=int(round(k0*BS));L=int(round(4*BS));r=lambda z:float(np.sqrt(np.mean(z**2))+1e-9)
      if i+L<=len(yb):
        g=r(y[i-L:i])/r(yb[i:i+L])*10**(-float(os.environ.get('LX_TRIM_DB',1.5))/20);yb=yb*float(np.clip(g,1.0,10**(9/20)))
    w=np.clip((np.arange(n)/BS-(k0-xf))/max(xf,1e-9),0,1).astype(np.float32)
    y=y*(1-w[:,None])+yb*w[:,None]
  for lane,kind,fc in (('low','low',XO),('high','high',HXO)):
    lp=d['auto'].get(lane) or []
    if not lp:continue
    t=np.arange(n)/BS+d['start_bar'];gl=np.interp(t,[p[0] for p in lp],[p[1] for p in lp]).astype(np.float32)
    nz=np.where(gl<0.9999)[0]
    if len(nz):
      a0,a1=max(0,nz[0]-SR),min(n,nz[-1]+SR);seg=y[a0:a1]
      band=sosfiltfilt(butter(4,fc,kind,fs=SR,output='sos'),seg,axis=0).astype(np.float32)
      y[a0:a1]=seg-band*(1-gl[a0:a1,None])
  eo=d.get('echo_out');src=y[-int(round(eo['bars']*BS)):].copy() if eo else None  # pre-fader final bars feed the delay
  pts=d['auto'].get('gain') or []
  if pts:
    t=np.arange(n)/BS+d['start_bar'];g=np.interp(t,[p[0] for p in pts],[p[1] for p in pts]).astype(np.float32);y*=g[:,None]
  return np.concatenate([y,echo_tail(src,eo)]) if eo else y
def _phase(seg):
  import sys;sys.path.insert(0,os.path.join(os.path.dirname(os.path.abspath(__file__)),'../src/tests'));import deckpair as P
  return P.beat_phase(P.snare_env(seg.mean(1)),per=BEAT/4,nb=2)
def _lx_shift(y,yb,k0):
  """ms to read the beat loop later (+) / earlier so its 16th-grid phase matches the 2 mix bars before the switch"""
  i=int(round(k0*BS));L=int(round(2*BS))
  if i-L<0 or i+L>len(yb):return 0
  a,b=_phase(y[i-L:i]),_phase(yb[i:i+L])
  return 0 if a is None or b is None else round(b-a,1)
def _bars(tr,m,x,n,extra=None):
  y=np.zeros((n+SEAM*2,2),np.float32)
  for k,sb in enumerate(m):
    i0=int(round(k*BS));L=int(round((k+1)*BS))-i0
    j0=int(round((tr['d0']+sb*BAR-nudge(tr,sb)/1000+(extra or {}).get(k,0)/1000)*SR))
    ex=extra or {};cont_prev=k>0 and sb==m[k-1]+1 and nudge(tr,sb)==nudge(tr,m[k-1]) and ex.get(k,0)==ex.get(k-1,0)
    cont_next=k<len(m)-1 and m[k+1]==sb+1 and nudge(tr,m[k+1])==nudge(tr,sb) and ex.get(k+1,0)==ex.get(k,0)
    pre=0 if cont_prev or k==0 else SEAM//2;post=0 if cont_next or k==len(m)-1 else SEAM//2
    a0=j0-pre;seg=x[max(0,a0):j0+L+post]
    if a0<0:seg=np.pad(seg,((-a0,0),(0,0)))
    seg=np.pad(seg,((0,max(0,pre+L+post-len(seg))),(0,0)))[:pre+L+post].copy()
    if pre:seg[:2*pre]*=np.linspace(0,1,2*pre,dtype=np.float32)[:,None]  # linear overlap-add seam (correlated material)
    if post:seg[-2*post:]*=np.linspace(1,0,2*post,dtype=np.float32)[:,None]
    o=SEAM+i0-pre;y[o:o+len(seg)]+=seg
  return y[SEAM:SEAM+n]
def echo_tail(src,eo):
  """Delay-tail exit: tempo-synced feedback delay (every delay_beats, each repeat fb x the last, first at wet_db) of the deck's
  pre-fader final bars, band-passed lo..hi Hz (low-cut keeps it off the incoming kick/bass); only the wet tail AFTER the deck's
  last sample (crossfader end) is returned, tail_bars long, starting on the blend's phrase boundary with a 5 ms fade-in."""
  x=sosfiltfilt(butter(4,[eo['lo'],eo['hi']],'band',fs=SR,output='sos'),src,axis=0).astype(np.float32);n=len(x);L=int(round(eo['tail_bars']*BS))
  out=np.zeros((n+L,2),np.float32);D=eo['delay_beats']*BEAT*SR;g=10**(eo['wet_db']/20);k=1
  while k*D<n+L and g>1e-4:
    o=int(round(k*D));m=min(n,n+L-o);out[o:o+m]+=g*x[:m];g*=eo['fb'];k+=1
  t=out[n:];f=int(0.005*SR);t[:f]*=np.linspace(0,1,f,dtype=np.float32)[:,None];return t
