"""Harness-only stretch-to-174 + grid, used when src2/prep.py rejects a source
as non-DnB. Does not modify the mixer. Same stretch/grid path as prep.py."""
import librosa, numpy as np, subprocess, json, sys, os
T=174.0
def grid(y,sr):
  per=60/T;hop=128
  oe=librosa.onset.onset_strength(y=y,sr=sr,hop_length=hop);ot=np.arange(len(oe))*hop/sr
  best=None
  for ph in np.arange(0,per,0.002):
    ts=np.arange(ph,ot[-1],per);s=np.interp(ts,ot,oe).sum()
    if best is None or s>best[0]:best=(s,ph)
  ph=best[1];beats=np.arange(ph,len(y)/sr-0.01,per)
  low=librosa.onset.onset_strength(y=y,sr=sr,hop_length=hop,fmax=150,n_mels=32)
  S=np.abs(librosa.stft(y,hop_length=hop));fr=librosa.fft_frequencies(sr=sr)
  rms=librosa.feature.rms(S=S)[0]
  def at(v,t):return np.interp(t,ot[:len(v)],v[:len(ot)])
  kick=at(low,beats);R=at(rms,beats)
  sc=[]
  for p in range(4):
    bars=beats[p::4];bR=np.array([R[i:i+4].mean() for i in range(p,len(R)-4,4)])
    nov=np.abs(np.diff(np.log(bR+1e-6))).sum()
    sc.append(kick[p::4].mean()/kick.mean()+ 2*nov/len(bR))
  p=int(np.argmax(sc));downs=beats[p::4]
  bR=np.array([R[p+4*i:p+4*i+4].mean() for i in range(len(downs))])
  lb=np.log(bR+1e-6);sc8=[]
  for q in range(8):
    sc8.append(np.abs(np.diff(lb))[q-1::8].sum() if q>0 else np.abs(np.diff(lb))[7::8].sum())
  q=int(np.argmax(sc8));phr=downs[q::8]
  return dict(per=per,beats=beats.tolist(),downs=downs.tolist(),phrases=phr.tolist(),barrms=bR.tolist())

f=sys.argv[1];b=os.path.splitext(os.path.basename(f))[0]
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src2'))
import pbpm
_bpm, _meta = pbpm.analyze(f)
# Prefer detector tempo even when genre-reject fired, so 161->174 stretch matches the DJ speed-up.
if _meta.get('bpm'):
  det=float(_meta['bpm'])
else:
  det=None
bpm=float(sys.argv[2]) if len(sys.argv)>2 else (det or 174.0)
if det and abs(det-174)>1 and 70 < det < 200:
  bpm=det
out=f'st/{b}.wav';os.makedirs('st',exist_ok=True)
tmp=f'st/{b}_in.wav'
subprocess.run(['ffmpeg','-loglevel','error','-y','-i',f,'-af','volume=-9dB','-c:a','pcm_f32le',tmp],check=True)
if abs(T/bpm-1)<2e-4: os.replace(tmp,out)
else:
  subprocess.run(['rubberband','-3','-F','-T',str(T/bpm),'-q',tmp,out],check=True); os.remove(tmp)
y2,_=librosa.load(out,sr=22050,mono=True)
g=grid(y2,22050);g['orig_bpm']=bpm;g['dur']=len(y2)/22050;g['forced']=True;g['pbpm_reason']=_meta.get('reason')
json.dump(g,open(f'st/{b}.json','w'))
print(b,round(bpm,3),'FORCE downs',len(g['downs']),'phr0',round(g['phrases'][0],2), _meta.get('reason'))
