import numpy as np,librosa,json,soundfile as sf,sys
f=sys.argv[1];y,sr=librosa.load(f,sr=22050);per=60/174;hop=64
oe=librosa.onset.onset_strength(y=y,sr=sr,hop_length=hop);ot=np.arange(len(oe))*hop/sr
W=10;res=[]
for t0 in np.arange(0,ot[-1]-W,W):
  m=(ot>=t0)&(ot<t0+W);o=oe[m];t=ot[m]
  ph=np.arange(0,per,0.001);s=[np.interp(np.arange(t0+p,t0+W,per),t,o).sum() for p in ph]
  # phase relative to global grid: (t0+p) mod per
  res.append(((t0+ph[int(np.argmax(s))])%per, max(s)/np.mean(s)))
ph=np.array([r[0] for r in res]);ref=np.angle(np.exp(2j*np.pi*ph/per).mean())*per/(2*np.pi)%per
dev=((ph-ref+per/2)%per-per/2)*1000
meta=json.load(open('mix_meta.json'))
for i,(d,r) in enumerate(zip(dev,res)):
  flag='  <-- off' if abs(d)>15 and r[1]>1.3 else ''
  print(f"{i*W//60:02d}:{i*W%60:02d} dev={d:+6.1f}ms peakiness={r[1]:.2f}{flag}")
