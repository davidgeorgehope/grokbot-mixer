"""Per-bar features the pair table needs beyond levels/drums/vocals (additive; never renders audio).
  chroma: 12-bin pitch-class profile of each source bar above 150 Hz (melody/chords, bass excluded)
  phase:  each source bar's 16th-note grid offset (ms) from its onset envelope; drift between two decks = flams
Cached as st/<id>.feat.npz.  python3 pair_feats.py  builds every crate track (8 workers)."""
import os,sys,json,numpy as np
BAR=4*60/174.0
# interval weights for clash: semitone (1/11) and tritone (6) rub, whole tone (2/10) mildly, consonances 0
IW=np.array([0,1,.35,0,0,0,.7,0,0,0,.35,1])
def build(b):
  f=f'st/{b}.feat.npz'
  if os.path.exists(f):return f
  import librosa
  y,sr=librosa.load(f'st/{b}.wav',sr=22050,mono=True);J=json.load(open(f'st/{b}.json'));d0=J['downs'][0]
  y=librosa.effects.harmonic(y,margin=2)
  S=np.abs(librosa.stft(y,n_fft=4096,hop_length=1024));fr=librosa.fft_frequencies(sr=sr,n_fft=4096);S[fr<150]=0
  ch=librosa.feature.chroma_stft(S=S**2,sr=sr,n_fft=4096,hop_length=1024);t=librosa.frames_to_time(np.arange(ch.shape[1]),sr=sr,hop_length=1024)
  nb=len(J['bar']['all']);E=np.zeros((nb,12));en=np.zeros(nb)
  for i in range(nb):
    m=(t>=d0+i*BAR)&(t<d0+(i+1)*BAR)
    if m.any():E[i]=ch[:,m].mean(1);en[i]=S[:,m].mean()
  o=np.load(f'st/{b}.onset.npy');ph=np.full(nb,np.nan);per=BAR/16;fpb=o.shape[1]
  for i in range(min(nb,len(o))):
    seg=o[i];g=np.arange(16)*fpb/16;offs=np.arange(-per/2,per/2,0.001)
    sc=np.array([seg[np.clip(np.round(g+x*fpb/BAR).astype(int),0,fpb-1)].mean() for x in offs])
    if sc.max()>=1.3*sc.mean()+1e-9:ph[i]=offs[sc.argmax()]*1000
  np.savez(f,chroma=E,harm_en=en,phase=ph);return f
def load(b):
  z=np.load(build(b));c=z['chroma'];n=c/(c.sum(1,keepdims=True)+1e-9);return n,z['harm_en'],z['phase']
def clash(ca,cb):
  """chord rub between two pitch-class profiles: sum_ij a_i b_j IW[|i-j|], 0..1"""
  M=IW[(np.arange(12)[:,None]-np.arange(12)[None,:])%12];return float(ca@M@cb)
if __name__=='__main__':
  sys.path.insert(0,'.');sys.path.insert(0,'../src/tests');os.environ.setdefault('MIX_SRC','.');import plan_search as P
  from multiprocessing import Pool
  with Pool(int(sys.argv[1]) if len(sys.argv)>1 else 8) as p:print(len(p.map(build,P.crate())),'tracks')
