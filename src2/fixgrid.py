import numpy as np,json,librosa,glob,sys
for f in sorted(glob.glob('st/*.json')):
  b=f[3:-5];g=json.load(open(f));beats=np.array(g['beats'])
  y,sr=librosa.load(f'st/{b}.wav',sr=22050)
  S=np.abs(librosa.stft(y,hop_length=128));fr=librosa.fft_frequencies(sr=sr);t=np.arange(S.shape[1])*128/sr
  lo=np.maximum(0,np.diff(S[fr<120].sum(0),prepend=0));mid=np.maximum(0,np.diff(S[(fr>1500)&(fr<5000)].sum(0),prepend=0))
  idx=np.searchsorted(t,beats)
  def pk(v):return np.array([v[max(0,i-3):i+5].max() if i<len(v) else 0 for i in idx])
  K=pk(lo);Sn=pk(mid);K/=K.mean();Sn/=Sn.mean()
  sc=[]
  for p in range(4):
    sc.append(K[p::4].mean()+Sn[(p+1)%4::4].mean()+Sn[(p+3)%4::4].mean()-Sn[p::4].mean()-0.5*Sn[(p+2)%4::4].mean())
  p=int(np.argmax(sc));downs=beats[p::4]
  rms=librosa.feature.rms(S=S)[0];R=np.interp(downs,t,np.convolve(rms,np.ones(40)/40,'same'))
  # phrase: section changes on 8-bar boundaries; combine with energy jumps
  lb=np.log(np.array([np.interp(np.arange(d,d+4*60/174,0.05),t,rms).mean() for d in downs])+1e-6)
  nov=np.abs(np.diff(lb));sc8=[nov[(q-1)%8::8].sum() for q in range(8)]
  q=int(np.argmax(sc8));g['downs']=downs.tolist();g['phrases']=downs[q::8].tolist()
  json.dump(g,open(f,'w'));print(b,'downphase',p,np.round(sc,2),'phrase',q,np.round(sc8,2))
