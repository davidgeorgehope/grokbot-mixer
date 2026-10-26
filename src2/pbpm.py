import librosa,numpy as np,sys
def pbpm(path):
  y,sr=librosa.load(path,sr=22050);hop=64
  oe=librosa.onset.onset_strength(y=y,sr=sr,hop_length=hop);ot=np.arange(len(oe))*hop/sr
  best=(0,0)
  for bpm in np.arange(170,177,0.01):
    per=60/bpm;n=int(ot[-1]/per)
    for ph in np.arange(0,per,per/24):
      s=np.interp(ph+np.arange(n)*per,ot,oe).sum()/n
      if s>best[0]:best=(s,bpm,ph)
  # refine
  b0=best[1]
  for bpm in np.arange(b0-0.02,b0+0.02,0.001):
    per=60/bpm;n=int(ot[-1]/per)
    for ph in np.arange(0,per,per/96):
      s=np.interp(ph+np.arange(n)*per,ot,oe).sum()/n
      if s>best[0]:best=(s,bpm,ph)
  return best[1]
if __name__=='__main__':
  for p in sys.argv[1:]:print(p,round(pbpm(p),3),flush=True)
