"""Beat-only (drums+bass) stem of a track for the synthetic-outro fallback ('lx' windows, the listener 2026-11-01:
"loop just the beat arrangement" when the real outro/loop doesn't work). Cached as st/<id>.dnb.wav (same scale as
st/<id>.wav, so the deck's -16 LUFS gain applies unchanged) + st/<id>.dnb_lv.npz (per-beat levels, like pair_feats.beats).
Demucs output goes to a temp dir that is deleted right after.  usage: python3 beatstem.py <id> [<id> ...]"""
import os,sys,json,shutil,subprocess,tempfile,numpy as np,soundfile as sf
BAR=4*60/174.0
def path(b):return f'st/{b}.dnb.wav'
def ensure(b):
  if os.path.exists(path(b)):return path(b)
  tmp=tempfile.mkdtemp(prefix='dnb_')
  try:
    subprocess.run([sys.executable,'-m','demucs','-n','htdemucs','-o',tmp,'--float32',f'st/{b}.wav'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    d=f'{tmp}/htdemucs/{b}';y=sf.read(f'{d}/drums.wav',dtype='float32',always_2d=True)[0]+sf.read(f'{d}/bass.wav',dtype='float32',always_2d=True)[0]
    sf.write(path(b)+'.part.wav',y,44100,subtype='FLOAT');os.replace(path(b)+'.part.wav',path(b))
  finally:shutil.rmtree(tmp,ignore_errors=True)
  return path(b)
def levels(b):
  """per-beat dB of the drums+bass stem (index = source bar*4 + beat), same grid as pair_feats.beats"""
  f=f'st/{b}.dnb_lv.npz'
  if os.path.exists(f):return np.load(f)['all']
  y=sf.read(ensure(b),dtype='float32',always_2d=True)[0].mean(1);J=json.load(open(f'st/{b}.json'));d0=J['downs'][0]
  nb=len(J['bar']['all'])*4;bt=BAR/4;A=np.full(nb,-120.)
  for i in range(nb):
    a,c=int((d0+i*bt)*44100),int((d0+(i+1)*bt)*44100)
    if c<=len(y) and a>=0:A[i]=20*np.log10(np.sqrt(np.mean(y[a:c]**2))+1e-9)
  np.savez(f,all=A);return A
if __name__=='__main__':
  for b in sys.argv[1:]:ensure(b);levels(b);print(b,'ok',flush=True)
_G={}
def lx_len(b,p,dip=4.0):
  """loop length of the beat-only phrase starting at p: 16 when drums and bass (<150 Hz) hold steady over p..p+15 (no bar more than
  `dip` dB under the phrase median), 8 when only the first 8 bars do (DnB beat fills sit in bars 13-16), 0 = no clean beat loop here.
  From the cached bar features only, so planning never needs the stems."""
  if b not in _G:g=json.load(open(f'st/{b}.json'))['bar'];d=np.array(g['drums'],float);_G[b]=(d,np.array(g['low'],float),d>np.percentile(d,75)-8)
  d,lo,on=_G[b]
  for L in (16,8):
    s=slice(p,p+L)
    if p+L<=len(d) and on[s].all() and all(np.min(x[s])>=np.median(x[s])-dip for x in (d,lo)):return L
  return 0
