"""Echo-out / delay-tail exits in Raveform DnB transitions (sample.json, audio/ segments, tracks/).
At the outgoing track's alignment end tE, fit each of the next 8 mix beats (150-9000 Hz power spectrum) as
gb*B(now) + gc*A(continuing) + ge*A(last beat before tE) with NNLS. Echo tail = A's last-beat spectrum still >= -12 dB of the
mix 1-2 beats after A stopped, above A-continuing, decaying; sync = mix onset envelope minus B's has a repeat at 1/2, 3/4 or 1 beat."""
import json,os,numpy as np,soundfile as sf,scipy.signal as ss,librosa
from scipy.optimize import nnls
R='/workspace/raveform/';SR=22050;S=json.load(open(R+'sample.json'))
F=np.fft.rfftfreq(2048,1/SR);MK=(F>=150)&(F<9000)
def E(x):return np.mean(np.abs(ss.stft(x,nperseg=2048,noverlap=1024)[2])**2,1)[MK]+1e-12 if x is not None and len(x)>=2048 else None
def al(mix,tid):
  for l in open(R+f'raveform/alignments/{mix}.align.jsonl'):
    a=json.loads(l)
    if a['track_id']==tid:return a
def mono(f):x,_=sf.read(f);return x.mean(1) if x.ndim>1 else x
rel=[json.loads(l) for l in open(R+'audio_results.jsonl')];rel={r['i']:r for r in rel if r.get('fit_r2_median',0)>=0.8}
out=[]
for i,t in enumerate(S):
  seg=R+f'audio/seg{i:02d}.wav';fa,fb=R+f'tracks/{t["a"]}.wav',R+f'tracks/{t["b"]}.wav'
  if not all(map(os.path.exists,(seg,fa,fb))):continue
  m,A,B=mono(seg),mono(fa),mono(fb);off=max(0,t['mix_t0']-30);ra,rb=al(t['mix'],t['a']),al(t['mix'],t['b'])
  rA=ra['matched_time_track']/ra['matched_time_mix'];rB=rb['matched_time_track']/rb['matched_time_mix']
  mb=np.array(json.load(open(R+f'raveform/beats/mixes/{t["mix"]}.beat.json'))['beats']);tE=ra['mixout_time_mix']
  pb=float(np.median(np.diff(mb[(mb>tE-30)&(mb<tE+30)])));bpm=60/pb
  if not 160<=bpm*(2 if bpm<100 else 1)<=180:continue
  mx=lambda a,b:m[int((a-off)*SR):int((b-off)*SR)] if a>=off and (b-off)*SR<=len(m) else None
  tr=lambda x,a,b:x[int(a*SR):int(b*SR)] if a>=0 and b*SR<=len(x) else None
  bt=lambda tm:rb['mixin_time_track']+(tm-rb['mixin_time_mix'])*rB
  at=lambda tm:ra['mixout_time_track']+(tm-tE)*rA
  # calibrate: B-only beats 8-16 after tE, A-only beats before B enters
  post=[(E(mx(tE+k*pb,tE+(k+1)*pb)),E(tr(B,bt(tE+k*pb),bt(tE+(k+1)*pb)))) for k in range(10,18)]
  pre=[(E(mx(tm,tm+pb)),E(tr(A,at(tm),at(tm+pb)))) for tm in np.arange(rb['mixin_time_mix']-8*pb,rb['mixin_time_mix']-pb,pb)]
  post=[p for p in post if p[0] is not None and p[1] is not None];pre=[p for p in pre if p[0] is not None and p[1] is not None]
  if len(post)<4 or len(pre)<3:continue
  kb=np.median([a/b for a,b in post],0);ka=np.median([a/b for a,b in pre],0)
  last=E(tr(A,at(tE-pb),at(tE)))
  if last is None:continue
  sh=[]
  for k in range(8):
    em=E(mx(tE+k*pb,tE+(k+1)*pb));eb=E(tr(B,bt(tE+k*pb),bt(tE+(k+1)*pb)));ec=E(tr(A,at(tE+k*pb),at(tE+(k+1)*pb)))
    if em is None or eb is None:break
    cols=[kb*eb,ka*last]+([ka*ec] if ec is not None else []);X=np.stack(cols,1);sc=em.sum()
    g,_=nnls(X/sc,em/sc);parts=[g[j]*cols[j].sum()/sc for j in range(len(cols))]
    sh.append((parts[1],parts[2] if len(parts)>2 else 0.0))
  if len(sh)<6:continue
  e=np.array([s[0] for s in sh]);c=np.array([s[1] for s in sh])
  # tempo-sync repeat check on beats 0-3 after tE: residual onset envelope autocorrelation at 1/2,3/4,1 beat vs off-grid lags
  x=mx(tE,tE+4*pb);y=tr(B,bt(tE),bt(tE+4*pb))
  if x is None or y is None:continue
  om=librosa.onset.onset_strength(y=x.astype(np.float32),sr=SR,hop_length=128);ob=librosa.onset.onset_strength(y=librosa.util.fix_length(y.astype(np.float32),size=len(x)),sr=SR,hop_length=128)
  n=min(len(om),len(ob));om,ob=om[:n],ob[:n];cb=float(om@ob/(ob@ob+1e-9));res=np.maximum(0,om-cb*ob);res=res-res.mean()
  ac=np.correlate(res,res,'full')[n-1:]/(res@res+1e-9);fr=pb*SR/128
  sync=max(ac[int(round(f*fr))] for f in (0.5,0.75,1.0));offg=max(ac[int(round(f*fr))] for f in (0.6,0.875,1.2))
  tail=int(np.sum(e>10**-1.5))  # beats with the last-beat echo >= -15 dB of the mix
  echo=bool(e[:2].max()>=10**-1.2 and e[:2].max()>2*c[:2].max() and e[4:8].mean()<e[:2].max() and sync>offg)
  out.append(dict(i=i,mix=t['mix'],reliable=i in rel,echo=echo,echo_db_beat1_2=round(10*np.log10(e[:2].max()+1e-6),1),cont_db=round(10*np.log10(c[:2].max()+1e-6),1),tail_beats=tail,sync=round(float(sync),2),offgrid=round(float(offg),2),
    a_out_frac=round(ra['mixout_time_track']/len(A)*SR,3),exit_in_overlap=round((tE-rb['mixin_time_mix'])/max(1e-3,tE-rb['mixin_time_mix']),2),ov_bars=round((tE-rb['mixin_time_mix'])/(4*pb),1),bpm=round(bpm,1)))
  print(json.dumps(out[-1]),flush=True)
json.dump(out,open(R+'echo/echo_results.json','w'),indent=1)
