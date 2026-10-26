import numpy as np,soundfile as sf,json,librosa,pyloudnorm as pyln,sys
from scipy.signal import butter,sosfiltfilt
SR=44100;T=174.0;BAR=4*60/T
order=json.load(open('order.json'))
XB=16  # overlap bars
def load(b):
  y,sr=sf.read(f'st/{b}.wav',dtype='float32',always_2d=True);assert sr==SR
  g=json.load(open(f'st/{b}.json'))
  m=pyln.Meter(SR);L=m.integrated_loudness(y);y=y*10**((-16-L)/20)
  return y,g
lp=butter(2,180,'low',fs=SR,output='sos');hp=butter(2,180,'high',fs=SR,output='sos')
hh=butter(2,2500,'high',fs=SR,output='sos')
def bands(y):
  lo=sosfiltfilt(lp,y,axis=0);hi=sosfiltfilt(hp,y,axis=0);return lo,hi
def onset(y,sr=SR):
  return librosa.onset.onset_strength(y=librosa.resample(y.mean(1),orig_sr=sr,target_sr=22050),sr=22050,hop_length=64)
def first_phrase(g,minT):
  ph=[p for p in g['phrases'] if p>=minT-0.05];return ph[0]
def audible_start(y):
  e=np.abs(y).mean(1);th=0.02*e.max();return np.argmax(e>th)/SR
def audible_end(y):
  e=np.abs(y).mean(1);th=0.02*e.max();return (len(e)-np.argmax(e[::-1]>th))/SR
tracks=[load(b) for b in order]
# per-track in/out points
pts=[]
for i,(y,g) in enumerate(tracks):
  st=0.0 if i==0 else first_phrase(g,max(0,audible_start(y)-BAR*0.5))
  # snap start to downbeat grid: use phrase grid
  end=audible_end(y)
  downs=np.array(g['downs']);ph=np.array(g['phrases'])
  # out: latest phrase boundary with XB bars before audible end
  cand=[p for p in ph if p+XB*BAR<=end+0.01 and p>st+60]
  out=cand[-1] if cand else downs[downs+XB*BAR<=end][-1]
  pts.append([st,out,end])
# allow override
try:
  ov=json.load(open('override.json'))
  for k,v in ov.items(): pts[order.index(k)][int(v[0])]=v[1]
except FileNotFoundError: pass
N=int(XB*BAR*SR)
mixlen=0;segs=[]
pos=0.0  # time in mix where track i 'st' lands
report=[]
for i,(y,g) in enumerate(tracks):
  st,out,end=pts[i]
  if i>0:
    # refine alignment by onset cross-correlation over overlap window
    yp,gp=tracks[i-1];po=pts[i-1][1]
    a=onset(yp[int(po*SR):int(po*SR)+N]);b=onset(y[int(st*SR):int(st*SR)+N])
    n=min(len(a),len(b));a=a[:n]-a[:n].mean();b=b[:n]-b[:n].mean()
    hopT=64/22050;maxl=int(0.02/hopT)
    cc=[np.dot(a[max(0,l):n+min(0,l)],b[max(0,-l):n-max(0,l)]) for l in range(-maxl,maxl+1)]
    lag=(np.argmax(cc)-maxl)*hopT
    pk=max(cc)/(np.linalg.norm(a)*np.linalg.norm(b)+1e-9)
    if pk<0.3: lag=0.0
    st=st-lag;pts[i][0]=st
    report.append(dict(into=order[i],lag_ms=round(lag*1000,1),xcorr_peak=round(float(max(cc)/ (np.linalg.norm(a)*np.linalg.norm(b)+1e-9)),3)))
  segs.append((pos,y,st,out,end))
  if i<len(tracks)-1: pos+= (out-st)
total=pos+(pts[-1][2]-pts[-1][0])+1
M=np.zeros((int(total*SR)+N,2),dtype=np.float32)
def ramp(n,a,b):return np.linspace(a,b,n,dtype=np.float32)[:,None]
starts=[]
for i,(p,y,st,out,end) in enumerate(segs):
  s0=int(st*SR);x=y[s0:].copy()
  L=len(x);gl=np.ones((L,1),np.float32);gh=np.ones((L,1),np.float32)
  half=N//2;beat=int(60/T*SR)
  if i>0: # incoming: bars 0-8 lows off, highs fade in; swap at bar 8
    gl[:half]=0;gl[half:half+beat]=ramp(beat,0,1)
    gh[:half]=np.sqrt(ramp(half,0,1))
  if i<len(segs)-1: # outgoing
    o=int((out-st)*SR)
    gl[o+half:]=0;gl[o+half-beat:o+half]=ramp(beat,1,0)
    gh[o+half:o+N]=np.sqrt(ramp(N-half,1,0));gh[o+N:]=0
    x=x[:o+N];gl=gl[:o+N];gh=gh[:o+N]
  lo,hi=bands(x)
  out_=lo*gl+hi*gh
  i0=int(p*SR);M[i0:i0+len(out_)]+=out_;starts.append(p)
M=M[:int(total*SR)]
np.save('mix_raw.npy',M);sf.write('mix_raw.wav',M,SR,subtype='FLOAT')
json.dump(dict(order=order,starts=starts,pts=pts,report=report),open('mix_meta.json','w'),indent=1)
print(json.dumps(report,indent=0));print('starts',[round(s,1) for s in starts],'len',round(total/60,2))
