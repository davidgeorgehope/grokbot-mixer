"""GPU side: per-deck ears check for every blend cut by ears_cut.py.
Usage: python ears_check.py CUTDIR [--device mps] [--out report.json]
Per deck: htdemucs stems -> Beat This on drums stem, Basic Pitch on vocals+other (melody).
Per blend (only bars where both decks are audible, gain>=GMIN):
  both_drum_bars  bars where both decks' drum stems are active (> -15 dB re that deck's loudest drum bar in the window)
  beat_ms_med/p90 |A beat - nearest B beat| over both-drum bars (ms)
  down_agree      share of A downbeats with a B downbeat within 70 ms (both-drum bars)
  diss            cross-deck pitch-class roughness of the melody stems, gain-weighted (0..1)
Verdict thresholds live in THRESH (calibrated on the Mix 03 refill: 33:50 bad, 30:31 good)."""
import sys,os,json,argparse,time,numpy as np,soundfile as sf
THRESH=dict(beat_ms_med=45.0,down_agree=0.5,MIN_BARS=4,GMIN=0.2)  # diss: report only (did not separate on calibration)
def verdict(m):
  """FAIL if both decks drum >=MIN_BARS bars together and their downbeats or beats disagree. diss is report-only."""
  if m['both_drum_bars']<THRESH['MIN_BARS'] or (m.get('down_agree') is None and m.get('beat_ms_med') is None):return 'n/a (few both-drum bars)'
  f=[]
  if m.get('down_agree') is not None and m['down_agree']<THRESH['down_agree']:f.append('downbeats disagree')
  if m.get('beat_ms_med') is not None and m['beat_ms_med']>THRESH['beat_ms_med']:f.append('beat flam/offset')
  return 'FAIL: '+', '.join(f) if f else 'PASS'
if len(sys.argv)>2 and sys.argv[1]=='--rescore':  # re-apply THRESH to an existing report, no GPU
  R=json.load(open(sys.argv[2]));R['thresh']=THRESH
  for m in R['blends']:m['verdict']=verdict(m)
  json.dump(R,open(sys.argv[2],'w'),indent=1);[print(m['k'],m['verdict']) for m in R['blends']];sys.exit()
ap=argparse.ArgumentParser();ap.add_argument('cut');ap.add_argument('--device',default='mps');ap.add_argument('--out',default='')
a=ap.parse_args();dev=a.device;J=json.load(open(f'{a.cut}/blends.json'));BAR=J['bar_sec'];SR=44100
import torch
from demucs.pretrained import get_model;from demucs.apply import apply_model
from beat_this.inference import Audio2Beats
from basic_pitch.inference import predict;from basic_pitch import ICASSP_2022_MODEL_PATH
dm=get_model('htdemucs').to(dev).eval();a2b=Audio2Beats(checkpoint_path='final0',device=dev,dbn=False)
R=np.zeros((12,12))
for i in range(12):
  for j in range(12):R[i,j]={1:1,6:.5,2:.35}.get(min((i-j)%12,(j-i)%12),0)
T=dict(demucs=0,beat=0,pitch=0)
def stems(p):
  t=time.time();y,_=sf.read(p,dtype='float32');x=torch.tensor(np.stack([y,y]))[None].to(dev)
  with torch.no_grad():s=apply_model(dm,x,device=dev,split=True,overlap=0.1)[0].mean(1).cpu().numpy()
  T['demucs']+=time.time()-t;n=dm.sources;return {k:s[n.index(k)] for k in n}
def pcs(y,tmp):
  t=time.time();sf.write(tmp,y,SR);_,_,notes=predict(tmp,ICASSP_2022_MODEL_PATH);os.remove(tmp)
  fr=np.arange(0,len(y)/SR,0.1);P=np.zeros((len(fr),12))
  for st,en,pi,am,_ in notes:P[(fr>=st)&(fr<en),pi%12]+=am
  T['pitch']+=time.time()-t;return fr,P
def drum_active(d,nb):
  L=int(BAR*SR);e=np.array([np.sqrt(np.mean(d[i*L:(i+1)*L]**2))+1e-9 for i in range(nb)]);db=20*np.log10(e/e.max());return db>-15
rep=[]
for r in J['blends']:
  k=r['k'];nb=r['end_bar']-r['start_bar'];ga,gb=np.array(r['ga']),np.array(r['gb'])
  S={t:stems(f"{a.cut}/t{k:02d}_{t}.flac") for t in 'AB'}
  aud=(ga>=THRESH['GMIN'])&(gb>=THRESH['GMIN'])
  both=aud&drum_active(S['A']['drums'],nb)&drum_active(S['B']['drums'],nb)
  t=time.time();bt={x:a2b(S[x]['drums'],SR) for x in 'AB'};T['beat']+=time.time()-t
  inb=lambda v:np.isin(np.minimum((v/BAR).astype(int),nb-1),np.where(both)[0])
  (ba,da),(bb,db)=bt['A'],bt['B'];m=dict(k=k,t0=r['t0'],a=r['a'],b=r['b'],bars=nb,both_audible=int(aud.sum()),both_drum_bars=int(both.sum()))
  BEAT=BAR/4;m['bt']={x:[np.round(bt[x][0],3).tolist(),np.round(bt[x][1],3).tolist()] for x in 'AB'}
  def phase(dn):
    if not len(dn):return None,0.
    ph=np.round((dn%BAR)/BEAT).astype(int)%4;c=np.bincount(ph,minlength=4);return int(c.argmax()),float(c.max()/c.sum())
  for x,(bx,dx) in (('A',(ba,da)),('B',(bb,db))):m[f'phase_{x}'],m[f'phase_{x}_share']=phase(dx[inb(dx)] if both.sum()>=2 else dx)
  if both.sum()>=2:
    xa,xb=ba[inb(ba)],bb[inb(bb)]
    if len(xa) and len(xb):
      off=np.minimum(np.array([np.min(np.abs(xb-v)) for v in xa]),BEAT/2)*1000
      m.update(beat_ms_med=float(np.median(off)),beat_ms_p90=float(np.percentile(off,90)))
    xd,yd=da[inb(da)],db[inb(db)]
    m['down_agree']=float(np.mean([np.min(np.abs(yd-v))<0.07 for v in xd])) if len(xd) and len(yd) else None
  m['verdict']=verdict(m)
  fa,PA=pcs(S['A']['vocals']+S['A']['other'],f'/tmp/ea{k}.wav');fb,PB=pcs(S['B']['vocals']+S['B']['other'],f'/tmp/eb{k}.wav')
  n=min(len(PA),len(PB));bi=np.minimum((fa[:n]/BAR).astype(int),nb-1);w=np.minimum(ga[bi],gb[bi])*aud[bi]
  sa,sb=PA[:n].sum(1),PB[:n].sum(1);ok=(sa>0)&(sb>0)&(w>0)
  num=np.einsum('ti,ij,tj->t',PA[:n],R,PB[:n]);dd=np.where(ok,num/(sa*sb+1e-9),0)
  m['diss']=float((dd*w).sum()/max(w[ok].sum(),1e-9)) if ok.any() else None
  m['diss_bars_p90']=float(np.percentile([dd[(bi==b)&ok].mean() for b in range(nb) if ((bi==b)&ok).any()] or [0],90))
  rep.append(m);print(json.dumps(m),flush=True)
out=dict(cut=J['meta'],device=dev,time=T,thresh=THRESH,blends=rep)
json.dump(out,open(a.out or f'{a.cut}/ears_report.json','w'),indent=1);print(T)
