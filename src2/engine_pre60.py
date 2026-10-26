import numpy as np,soundfile as sf,json,os,pyloudnorm as pyln
from scipy.signal import butter,sosfiltfilt,stft,istft
SR=44100;T=174.0;BEAT=60/T;BAR=4*BEAT;BS=BAR*SR
lp=butter(2,180,'low',fs=SR,output='sos');hp=butter(2,180,'high',fs=SR,output='sos')
lp2=butter(2,2500,'low',fs=SR,output='sos');hp2=butter(2,2500,'high',fs=SR,output='sos')
_cache={}
def track(b):
  if b in _cache:return _cache[b]
  y,_=sf.read(f'st/{b}.wav',dtype='float32',always_2d=True)
  g=json.load(open(f'st/{b}.json'))
  L=pyln.Meter(SR).integrated_loudness(y);gain=10**((-16-L)/20)
  st={'mix':y*gain}
  d=f'sep/htdemucs/{b}'
  for s in ['vocals','drums']:
    if os.path.exists(f'{d}/{s}.wav'):
      z,_=sf.read(f'{d}/{s}.wav',dtype='float32',always_2d=True);z=z[:len(y)]
      if len(z)<len(y):z=np.pad(z,((0,len(y)-len(z)),(0,0)))
      st[s]=z*gain
  lo=np.array(g['bar']['low']);bass=lo>np.percentile(lo,90)-8
  # runs of bass
  runs=[];i=0
  while i<len(bass):
    if bass[i]:
      j=i
      while j<len(bass) and (bass[j] or (j+1<len(bass) and bass[j+1] and j+2<len(bass) and bass[j+2])):j+=1
      if j-i>=8:runs.append([i,j])
      i=j
    else:i+=1
  voc=np.array(g['bar'].get('voc',[-100]*len(lo)));vact=voc>np.percentile(voc,95)-14
  info=dict(id=b,g=g,st=st,d0=g['downs'][0],nb=len(g['downs']),runs=runs,bass=bass,vact=vact)
  _cache[b]=info;return info
import os as _os
NUDGE=json.load(open('nudge.json')) if _os.path.exists('nudge.json') else {}  # warp-marker style per-source-bar nudges (ms) for off-grid sections
def nudge(tr,k): return NUDGE.get(tr['id'],{}).get(str(k),0)
def srcbar(tr,k,stem='mix'):
  x=tr['st'][stem] if stem!='inst' else tr['st']['mix']-tr['st']['vocals']
  i0=int(round((tr['d0']+k*BAR-nudge(tr,k)/1000)*SR));n=int(round(BS))
  seg=x[i0:i0+n]
  if len(seg)<n:seg=np.pad(seg,((0,n-len(seg)),(0,0)))
  return seg
class Deck:
  def __init__(s,b,start,first_bar,nbars,label=''):
    s.tr=track(b);s.b=b;s.start=start;s.map=[(first_bar+i,'mix') for i in range(nbars)]
    s.auto={k:[] for k in ['low','mid','high','voc','hpf','gain']};s.label=label;s.echo=None
  def end(s):return s.start+len(s.map)
  def set(s,k,bar,val):s.auto[k].append((bar,val))
  def curve(s,k,default,n):
    pts=sorted(s.auto[k]);t=(np.arange(n)/BS)+s.start
    if not pts:return np.full(n,default,np.float32)
    xs=[p[0] for p in pts];ys=[p[1] for p in pts]
    return np.interp(t,xs,ys).astype(np.float32)
  def render(s):
    fade=256
    def build(stem):
      parts=[];prev=None
      for k,(sb,stm) in enumerate(s.map):
        if stem=='vocals' and stm!='mix' and stm!='vocals': seg=np.zeros((int(round(BS)),2),np.float32)
        else: seg=srcbar(s.tr,sb,stem if stem=='vocals' else stm)
        seg=seg.copy()
        if prev is not None and (sb!=prev[0]+1 or stm!=prev[1] or nudge(s.tr,sb)!=nudge(s.tr,prev[0])):
          seg[:fade]*=np.linspace(0,1,fade)[:,None]
          if parts:parts[-1][-fade:]*=np.linspace(1,0,fade)[:,None]
        parts.append(seg);prev=(sb,stm)
      return np.concatenate(parts)
    x=build('mix');n=len(x)
    if 'vocals' in s.tr['st']:
      v=build('vocals');gv=s.curve('voc',1,n)
      x=x-(1-gv)[:,None]*v
    lo=sosfiltfilt(lp,x,axis=0);rest=x-lo;mid=sosfiltfilt(lp2,rest,axis=0);hi=rest-mid
    y=lo*s.curve('low',1,n)[:,None]+mid*s.curve('mid',1,n)[:,None]+hi*s.curve('high',1,n)[:,None]
    fc=s.curve('hpf',0,n)
    if fc.max()>25:
      f,t,Z=stft(y.T,fs=SR,nperseg=4096,noverlap=3072)
      fct=np.interp(t,np.arange(n)/SR,fc)[None,:];F=f[:,None]+1e-3
      m=np.where(fct>25,(F/fct)**4/(1+(F/fct)**4),1.0)**0.5
      _,yy=istft(Z*m[None],fs=SR,nperseg=4096,noverlap=3072);y=yy.T[:n]
      if len(y)<n:y=np.pad(y,((0,n-len(y)),(0,0)))
    y=y*s.curve('gain',1,n)[:,None]
    return y
def echo_tail(x_lastbeat,fb=0.55,div=0.5,reps=14):
  d=int(round(BEAT*div*SR));src=sosfiltfilt(butter(2,300,'high',fs=SR,output='sos'),x_lastbeat,axis=0)
  out=np.zeros((d*(reps+1)+len(src),2),np.float32)
  for k in range(1,reps+1):
    c=max(1200,9000/(1+0.35*k));seg=sosfiltfilt(butter(2,c,'low',fs=SR,output='sos'),src,axis=0)*fb**k
    if k%2:seg=seg[:,::-1]*np.array([1,0.8])  # ping-pong-ish
    out[k*d:k*d+len(seg)]+=seg
  return out
