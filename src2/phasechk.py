import numpy as np,librosa,json,sys
T=174;BEAT=60/T;BAR=4*BEAT
for b in sys.argv[1:]:
  y,sr=librosa.load(f'st/{b}.wav',sr=22050);hop=64;o=librosa.onset.onset_strength(y=y,sr=sr,hop_length=hop);fr=sr/hop
  d=json.load(open(f'st/{b}.json'))['downs'];out=[]
  for k in range(0,len(d)-4,8):
    t0=d[k];per=BEAT/2;offs=np.arange(-0.04,0.04,0.001);g=t0+np.arange(0,4*BAR,per)
    sc=[o[np.clip(np.round((g+x)*fr).astype(int),0,len(o)-1)].mean() for x in offs];s=np.array(sc)
    out.append(int(offs[s.argmax()]*1000) if s.max()>1.3*s.mean() else None)
  print(b,out)
