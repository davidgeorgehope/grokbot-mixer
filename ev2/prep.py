"""Ears v2 data prep (box). 8-bar log-mel windows of a mixdown -> label 1 = clashing blend, 0 = clean.
Clean: pro-set segments, pro transitions, bar-aligned overlays. Bad (synthetic): overlays shifted off the beat grid, or a semitone off."""
import json,sys,numpy as np,librosa
from multiprocessing import Pool
SR=22050;rng=np.random.default_rng(0)
SETS=['dimension_allstars360','hospital_podcast393','wilkinson_boomtown2026']
def mel(y,W=int(8*(240/174)*SR)):y=np.pad(y,(0,max(0,W-len(y))))[:W];return librosa.power_to_db(librosa.feature.melspectrogram(y=y,sr=SR,n_mels=64,hop_length=512),ref=1.0).astype(np.float16)
def job(n):
  d=json.load(open(f'eval/sets/{n}.json'));y,_=librosa.load(f'pro_sets/wav/{n}.wav',sr=SR,mono=True)
  bar=240/d['bpm'];L=int(8*bar*SR);W=int(8*(240/174)*SR);r=np.random.default_rng(hash(n)%999);X=[];Y=[];K=[]
  def seg(t):i=int(t*SR);s=y[i:i+L];return librosa.resample(s,orig_sr=174.0,target_sr=d['bpm'])[:W] if len(s)==L else None  # tempo-normalise to 174
  N=len(y)/SR-20
  for t in (d.get('anchors') or []):
    for o in (-8,-4,0,4):
      s=seg(t+o*bar)
      if s is not None:X.append(mel(s));Y.append(0);K.append(0)
  for _ in range(900):
    t=r.uniform(10,N);a=seg(t)
    if a is None:continue
    kind=r.integers(5)
    if kind==0:X.append(mel(a));Y.append(0);K.append(1);continue
    nb=int(r.integers(8,64))*(1 if t<N/2 else -1);b=seg(t+nb*bar)
    if b is None:continue
    g=r.uniform(.5,1)
    if kind==1:z=a+g*b;lab=0;k=2                                     # bar-aligned overlay (drift-free grid)
    elif kind in(2,3):                                               # off-grid: half-beat, beat, 16th or 30-120 ms
      sh=r.choice([W/32,W/16,W/8*1.5,W/8,r.uniform(.03,.12)*SR]);b=np.roll(b,int(sh));z=a+g*b;lab=1;k=3
    else:b=librosa.effects.pitch_shift(b,sr=SR,n_steps=float(r.choice([-1,1,6])));z=a+g*b;lab=1;k=4
    z=z/(np.abs(z).max()+1e-9)*0.9;X.append(mel(z));Y.append(lab);K.append(k)
  return np.stack(X),np.array(Y),np.array(K),np.full(len(Y),SETS.index(n))
if __name__=='__main__':
  with Pool(3) as p:R=p.map(job,SETS)
  X,Y,K,S=[np.concatenate(z) for z in zip(*R)];np.savez_compressed('ev2/train.npz',X=X,Y=Y,K=K,S=S);print(X.shape,Y.mean())
