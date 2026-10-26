import numpy as np,librosa
def drift(path,T=174.0):
  y,sr=librosa.load(path,sr=22050);per=60/T;hop=64
  oe=librosa.onset.onset_strength(y=y,sr=sr,hop_length=hop);ot=np.arange(len(oe))*hop/sr
  W=10;ph=[];tc=[];wt=[]
  for t0 in np.arange(0,ot[-1]-W,W):
    m=(ot>=t0)&(ot<t0+W);o=oe[m];t=ot[m];P=np.arange(0,per,0.001)
    s=np.array([np.interp(np.arange(t0+p,t0+W,per),t,o).sum() for p in P])
    ph.append((t0+P[s.argmax()])%per);tc.append(t0+W/2);wt.append(s.max()/s.mean())
  ph=np.unwrap(np.array(ph)*2*np.pi/per)*per/(2*np.pi);wt=np.array(wt);k=wt>1.5
  sl=np.polyfit(np.array(tc)[k],ph[k],1)[0]
  return sl  # seconds of phase per second; actual period = per*(1+?)
