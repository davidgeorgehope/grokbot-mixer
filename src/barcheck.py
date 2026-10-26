import numpy as np,soundfile as sf,json,librosa
m=json.load(open('mix_meta.json'));order=m['order'];pts=m['pts'];T=174;per=60/T;BAR=4*per;XB=16
def pat(b,t0,nb):  # per-beat kick & snare strength folded by 4
  y,sr=librosa.load(f'st/{b}.wav',sr=22050,offset=max(0,t0-0.1),duration=nb*BAR+0.2);off=0.1 if t0>=0.1 else t0
  S=np.abs(librosa.stft(y,hop_length=128));fr=librosa.fft_frequencies(sr=sr);t=np.arange(S.shape[1])*128/sr
  lo=np.maximum(0,np.diff(S[fr<120].sum(0),prepend=0));mid=np.maximum(0,np.diff(S[(fr>1500)&(fr<5000)].sum(0),prepend=0))
  K=np.zeros(4);Sn=np.zeros(4)
  for k in range(nb*4):
    bt=off+k*per;w=(t>=bt-0.03)&(t<bt+0.05);K[k%4]+=lo[w].max() if w.any() else 0;Sn[k%4]+=mid[w].max() if w.any() else 0
  return K/K.sum(),Sn/Sn.sum()
for i in range(1,len(order)):
  a=order[i-1];b=order[i]
  # compare A's 16 bars before its out-point (full drums) with B's bars 16-32 (post-swap, drums in)
  Ka,Sa=pat(a,pts[i-1][1]-16*BAR,16);Kb,Sb=pat(b,pts[i][0]+16*BAR,16)
  v=np.concatenate([Ka,Sa]);best=[]
  for s in range(4):
    w=np.concatenate([np.roll(Kb,s),np.roll(Sb,s)]);best.append(np.dot(v,w))
  print(f"{a}->{b} bestshift={int(np.argmax(best))} scores={np.round(best,3)} A_kick={np.round(Ka,2)} B_kick={np.round(Kb,2)} A_sn={np.round(Sa,2)} B_sn={np.round(Sb,2)}")
