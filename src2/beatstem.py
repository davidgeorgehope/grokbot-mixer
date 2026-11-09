"""Beat-only (drums+bass) stem of a track for the synthetic-outro fallback ('lx' windows, the listener 2026-11-01:
"loop just the beat arrangement" when the real outro/loop doesn't work). Cached as st/<id>.dnb.wav (same scale as
st/<id>.wav, so the deck's -16 LUFS gain applies unchanged) + st/<id>.dnb_lv.npz (per-beat levels, like pair_feats.beats).
Demucs output goes to a temp dir that is deleted right after.  usage: python3 beatstem.py <id> [<id> ...]"""
import os,sys,json,shutil,subprocess,tempfile,threading,fcntl,numpy as np,soundfile as sf
BAR=4*60/174.0
_TLOCKS={};_TLOCKS_GUARD=threading.Lock()
def _tlock(key):
  with _TLOCKS_GUARD:
    return _TLOCKS.setdefault(key,threading.Lock())
class _FLock:
  """Cross-process exclusive lock. flock alone is not a mutex for threads in one process (Linux)."""
  def __init__(self,p):self.p=p+'.lock';self.fd=None
  def __enter__(self):
    self.fd=os.open(self.p,os.O_CREAT|os.O_RDWR);fcntl.flock(self.fd,fcntl.LOCK_EX);return self
  def __exit__(self,*_):
    fcntl.flock(self.fd,fcntl.LOCK_UN);os.close(self.fd)
def path(b):return f'st/{b}.dnb.wav'
def _atomic_write(dest,write):
  d=os.path.dirname(os.path.abspath(dest)) or '.'
  fd,part=tempfile.mkstemp(prefix=os.path.basename(dest)+'.',suffix='.part',dir=d)
  os.close(fd)
  try:
    write(part);os.replace(part,dest)
  finally:
    if os.path.exists(part):
      try:os.remove(part)
      except FileNotFoundError:pass
def ensure(b):
  p=path(b)
  if os.path.exists(p):return p
  with _tlock('dnb:'+b):
    if os.path.exists(p):return p
    with _tlock('demucs'),_FLock('st/.dnb_demucs'):
      if os.path.exists(p):return p
      tmp=tempfile.mkdtemp(prefix='dnb_')
      try:
        print(f'beatstem: building drums+bass cache for {b}',flush=True)
        subprocess.run([sys.executable,'-m','demucs','-n','htdemucs','-o',tmp,'--float32',f'st/{b}.wav'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        d=f'{tmp}/htdemucs/{b}';y=sf.read(f'{d}/drums.wav',dtype='float32',always_2d=True)[0]+sf.read(f'{d}/bass.wav',dtype='float32',always_2d=True)[0]
        _atomic_write(p,lambda part:sf.write(part,y,44100,subtype='FLOAT'))
      finally:shutil.rmtree(tmp,ignore_errors=True)
  return p
def levels(b):
  """per-beat dB of the drums+bass stem (index = source bar*4 + beat), same grid as pair_feats.beats"""
  f=f'st/{b}.dnb_lv.npz'
  if os.path.exists(f):return np.load(f)['all']
  with _tlock('lv:'+b):
    if os.path.exists(f):return np.load(f)['all']
    y=sf.read(ensure(b),dtype='float32',always_2d=True)[0].mean(1);J=json.load(open(f'st/{b}.json'));d0=J['downs'][0]
    nb=len(J['bar']['all'])*4;bt=BAR/4;A=np.full(nb,-120.)
    for i in range(nb):
      a,c=int((d0+i*bt)*44100),int((d0+(i+1)*bt)*44100)
      if c<=len(y) and a>=0:A[i]=20*np.log10(np.sqrt(np.mean(y[a:c]**2))+1e-9)
    _atomic_write(f,lambda part:np.savez(part,all=A));return A
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
