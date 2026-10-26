import librosa,numpy as np,json,sys,glob,os
maj=np.array([6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88]);mnr=np.array([6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17])
N=['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
CAM_MAJ={0:'8B',7:'9B',2:'10B',9:'11B',4:'12B',11:'1B',6:'2B',1:'3B',8:'4B',3:'5B',10:'6B',5:'7B'}
CAM_MIN={9:'8A',4:'9A',11:'10A',6:'11A',1:'12A',8:'1A',3:'2A',10:'3A',5:'4A',0:'5A',7:'6A',2:'7A'}
res={}
for f in sorted(glob.glob('wav/*.wav'))+(['../ai/ai.wav'] if os.path.exists('../ai/ai.wav') else []):
  y,sr=librosa.load(f,sr=22050,mono=True)
  oe=librosa.onset.onset_strength(y=y,sr=sr)
  t,_=librosa.beat.beat_track(onset_envelope=oe,sr=sr,start_bpm=172)
  t=float(np.atleast_1d(t)[0])
  if t<120:t*=2
  ch=librosa.feature.chroma_cqt(y=librosa.effects.harmonic(y),sr=sr).mean(1)
  best=max([(np.corrcoef(np.roll(maj,k),ch)[0,1],k,'maj') for k in range(12)]+[(np.corrcoef(np.roll(mnr,k),ch)[0,1],k,'min') for k in range(12)])
  _,k,m=best
  res[os.path.basename(f)]=dict(bpm=round(t,2),key=N[k]+(' min' if m=='min' else ' maj'),camelot=(CAM_MIN if m=='min' else CAM_MAJ)[k],dur=len(y)/sr)
  print(f,res[os.path.basename(f)],flush=True)
json.dump(res,open('analysis.json','w'),indent=1)
