"""Held-out: the listener's per-blend ratings -> 8-bar windows around each rated moment (t-15s..t+30s, hop 2.76 s)."""
import numpy as np,librosa,sys;sys.path.insert(0,'ev2');from prep_b import mel,SR
W=int(8*(240/174)*SR)
R=[('dj-mix-03-60-refill.mp3','15:00',2,'ears?'),('dj-mix-03-60-refill.mp3','30:56',5,'ears?'),('dj-mix-03-60-refill.mp3','34:05',1,'confirmed'),
   ('ev2/audio/mix04.mp3','24:16',3.5,'suspect'),('ev2/audio/mix03v2.mp3','2:57',3,'suspect'),('ev2/audio/mix03v2.mp3','51:52',4,'suspect'),
   ('ev2/audio/mix05n.mp3','5:53',3,'suspect'),('ev2/audio/mix05n.mp3','41:12',3,'suspect')]
X=[];G=[]
for i,(f,t,r,c) in enumerate(R):
  m,s=t.split(':');t0=int(m)*60+int(s);y,_=librosa.load(f,sr=SR,mono=True,offset=t0-15,duration=60)
  for j in range(0,len(y)-W,W//4)[:13]:X.append(mel(y[j:j+W]));G.append(i)
np.savez_compressed('ev2/held_b.npz',X=np.stack(X),G=np.array(G),R=np.array([r for *_,r,c in R]),C=np.array([c for *_,c in R]),T=np.array([f.split('/')[-1]+'@'+t for f,t,*_ in R]))
print(len(X))
