# self-made FX (synthesised here, no samples): riser, impact/sub-drop, reverse swell
import numpy as np,soundfile as sf
from scipy.signal import butter,sosfilt,sosfiltfilt
SR=44100;BAR=4*60/174;rng=np.random.default_rng(7)
def riser(bars=8):
  n=int(bars*BAR*SR);t=np.arange(n)/SR;x=rng.standard_normal((n,2))
  out=np.zeros_like(x);blk=2048
  for i in range(0,n,blk):
    fc=300*(12000/300)**(i/n);sos=butter(2,[fc*0.7,min(fc*1.4,20000)],'band',fs=SR,output='sos')
    out[i:i+blk]=sosfilt(sos,x[i:i+blk],axis=0)
  env=(t/t[-1])**2.2;out*=env[:,None]
  # rising sine sweep layer
  f=200*(2000/200)**(t/t[-1]);s=np.sin(2*np.pi*np.cumsum(f)/SR)*0.15*env
  out+=s[:,None];return out/np.abs(out).max()*0.5
def impact():
  n=int(3*SR);t=np.arange(n)/SR
  f=70*np.exp(-t*1.2)+32;sub=np.sin(2*np.pi*np.cumsum(f)/SR)*np.exp(-t*1.6)
  nz=rng.standard_normal((n,2))*np.exp(-t*3.5)[:,None];nz=sosfiltfilt(butter(2,[200,9000],'band',fs=SR,output='sos'),nz,axis=0)
  x=sub[:,None]*0.9+nz*0.35;return x/np.abs(x).max()*0.6
sf.write('fx/riser8.wav',riser(8),SR,subtype='FLOAT');sf.write('fx/riser4.wav',riser(4),SR,subtype='FLOAT');sf.write('fx/impact.wav',impact(),SR,subtype='FLOAT')
print('fx ok')
