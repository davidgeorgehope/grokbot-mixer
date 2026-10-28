# stretch each track to 174 BPM, build beat/downbeat/phrase grid
import librosa,numpy as np,soundfile as sf,subprocess,json,sys,os
import pbpm
T=174.0;SR=44100
def true_bpm(y,sr):
  oe=librosa.onset.onset_strength(y=y,sr=sr,hop_length=256)
  _,b=librosa.beat.beat_track(onset_envelope=oe,sr=sr,hop_length=256,start_bpm=172,tightness=400,units='time')
  d=np.diff(b);m=np.median(d);ok=np.abs(d-m)<0.1*m
  idx=np.concatenate([[0],np.cumsum(np.round(d/m))]).astype(int)
  # robust linear fit
  A=np.vstack([idx,np.ones_like(idx)]).T;p=np.linalg.lstsq(A,b,rcond=None)[0]
  r=b-A@p;keep=np.abs(r)<0.03;p=np.linalg.lstsq(A[keep],b[keep],rcond=None)[0]
  bpm=60/p[0]
  if bpm<120:bpm*=2
  return bpm
def grid(y,sr):
  per=60/T;hop=128
  oe=librosa.onset.onset_strength(y=y,sr=sr,hop_length=hop);ot=np.arange(len(oe))*hop/sr
  # phase search: comb fit
  best=None
  for ph in np.arange(0,per,0.002):
    ts=np.arange(ph,ot[-1],per);s=np.interp(ts,ot,oe).sum()
    if best is None or s>best[0]:best=(s,ph)
  ph=best[1];beats=np.arange(ph,len(y)/sr-0.01,per)
  # low band kick strength per beat, rms per beat
  low=librosa.onset.onset_strength(y=librosa.effects.preemphasis(y,coef=-0.97) if False else y,sr=sr,hop_length=hop,fmax=150,n_mels=32)
  S=np.abs(librosa.stft(y,hop_length=hop));fr=librosa.fft_frequencies(sr=sr)
  lowE=S[fr<120].sum(0);rms=librosa.feature.rms(S=S)[0]
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
y,sr=librosa.load(f,sr=22050,mono=True)
# Reject non-DnB before stretching (pbpm searches 70-180; UK-breaks like original Just Hold On fail here)
_bpm, _meta = pbpm.analyze(f)
if not _meta['ok']:
  raise SystemExit(f"prep REJECT {b}: not DnB ({_meta['reason']}) tops={_meta['tops'][:3]} dnb={_meta['dnb']} breaks={_meta['breaks']}")
bpm=float(sys.argv[2]) if len(sys.argv)>2 else float(_meta['bpm'])
# If caller passed a bpm, still require detector OK; prefer detector bpm when close
if abs(bpm - _meta['bpm']) > 3:
  print(f'WARN {b}: caller bpm {bpm} vs detector {_meta["bpm"]:.3f} ({_meta["reason"]}); using detector', flush=True)
  bpm=float(_meta['bpm'])
out=f'st/{b}.wav';os.makedirs('st',exist_ok=True)
tmp=f'st/{b}_in.wav'
subprocess.run(['ffmpeg','-loglevel','error','-y','-i',f,'-af','volume=-9dB','-c:a','pcm_f32le',tmp],check=True)
if abs(T/bpm-1)<2e-4: os.replace(tmp,out)
else:
  subprocess.run(['rubberband','-3','-F','-T',str(T/bpm),'-q',tmp,out],check=True); os.remove(tmp)
y2,_=librosa.load(out,sr=22050,mono=True)
g=grid(y2,22050);g['orig_bpm']=bpm;g['dur']=len(y2)/22050
json.dump(g,open(f'st/{b}.json','w'))
print(b,round(bpm,3),'downs',len(g['downs']),'phr0',round(g['phrases'][0],2))
