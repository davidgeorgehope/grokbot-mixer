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
def beats(b):
  """per-beat level (dB, full band and <150 Hz) of the source: entry/bass-swap level steps and near-silent spans (guardrails N1/E2/L1)"""
  f=f'st/{b}.beat.npz'
  if os.path.exists(f):z=np.load(f);return z['all'],z['low']
  import soundfile as sf;from scipy.signal import butter,sosfiltfilt
  y,sr=sf.read(f'st/{b}.wav',dtype='float32');y=y.mean(1) if y.ndim>1 else y;J=json.load(open(f'st/{b}.json'));d0=J['downs'][0]
  lo=sosfiltfilt(butter(4,150,'low',fs=sr,output='sos'),y);nb=len(J['bar']['all'])*4;bt=BAR/4;A=np.full(nb,-120.);L=np.full(nb,-120.)
  for i in range(nb):
    a,c=int((d0+i*bt)*sr),int((d0+(i+1)*bt)*sr)
    if c<=len(y) and a>=0:A[i]=20*np.log10(np.sqrt(np.mean(y[a:c]**2))+1e-9);L[i]=20*np.log10(np.sqrt(np.mean(lo[a:c]**2))+1e-9)
  np.savez(f,all=A,low=L);return A,L
def pattern(b):
  """per source bar: the ears test's 16-step kick+snare pattern (src/tests/ears.py), for predicting beat-off bars (backbeats on different beats)"""
  f=f'st/{b}.pat.npy'
  if os.path.exists(f):return np.load(f)
  import soundfile as sf;sys.path.insert(0,'../src/tests');import ears as E
  y,sr=sf.read(f'st/{b}.wav',dtype='float32');d0=json.load(open(f'st/{b}.json'))['downs'][0];P=E.pattern(y[max(0,int(d0*sr)):]);np.save(f,P);return P
def load(b):
  z=np.load(build(b));c=z['chroma'];n=c/(c.sum(1,keepdims=True)+1e-9);return n,z['harm_en'],z['phase']
def clash(ca,cb):
  """chord rub between two pitch-class profiles: sum_ij a_i b_j IW[|i-j|], 0..1"""
  M=IW[(np.arange(12)[:,None]-np.arange(12)[None,:])%12];return float(ca@M@cb)
if __name__=='__main__':
  sys.path.insert(0,'.');sys.path.insert(0,'../src/tests');os.environ.setdefault('MIX_SRC','.');import plan_search as P
  import multiprocessing as mp;Pool=mp.get_context('spawn').Pool  # fork + librosa threads deadlocked 2 of 50 workers
  with Pool(int(sys.argv[1]) if len(sys.argv)>1 else 8) as p:print(len(p.map(build,P.crate())),len(p.map(beats,P.crate())),len(p.map(pattern,P.crate())),'tracks')
