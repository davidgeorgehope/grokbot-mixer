#!/usr/bin/env python3
"""Master-gain auto-step (RCA 2026-11-24 fix 2): pick the master gain by rule before the full QA, instead of
render -> guardrails + pytest (35 min to hours) -> fail P1 -> remaster at a lower gain -> QA again.
The approved chain (src/master.sh) is unchanged; only its gain argument is chosen, and TP_MAX stays -1.0 dBTP.

Method (default, exact): master the whole raw mix with src/master.sh at the start gain, measure the encoded MP3 true peak with
the same meter as guardrails P1 / checks.true_peak (ffmpeg ebur128 peak=true), and step down by STEP dB until it is <= TP_MAX.
Each step is one full master (~1-2 min), so the expensive QA runs once, on a master that already passes P1.
An excerpt-only shortcut (--excerpts: the loudest / peakiest 20 s windows) was tried first and is kept for comparison only:
on Mix 10 r6c it read -1.50 dBTP at gain 9.0 while the full master read -0.8 (the peak was outside the picked windows).
usage: python3 gain_step.py RAW.wav [--start 9.0] [--floor 7.0] [--step 0.5] [--excerpts] [--out-mp3 X.mp3 --out-master X_master.wav]"""
import os,sys,re,json,subprocess,tempfile,argparse,numpy as np,soundfile as sf
HERE=os.path.dirname(os.path.abspath(__file__));ROOT=os.path.dirname(HERE);MASTER=os.path.join(ROOT,'src/master.sh')
TP_MAX=-1.0
def tp_of(mp3):
  o=subprocess.run(['ffmpeg','-nostats','-i',mp3,'-af','ebur128=peak=true','-f','null','-'],capture_output=True,text=True).stderr
  s=o[o.rfind('Summary'):];return float(re.search(r'Peak:\s+(-?[\d.]+|-inf)',s.split('True peak')[1]).group(1).replace('-inf','-120'))
def windows(raw,k=4,sec=20.0):
  """[(start_s, dur_s)] K loudest-RMS and K highest-peak non-overlapping windows"""
  info=sf.info(raw);sr=info.samplerate;W=int(sec*sr);rms=[];pk=[]
  for i,blk in enumerate(sf.blocks(raw,blocksize=W,dtype='float32',always_2d=True)):
    if len(blk)<W//2:continue
    m=blk.mean(1);rms.append((float(np.sqrt(np.mean(m**2))),i));pk.append((float(np.abs(blk).max()),i))
  pick=sorted(set([i for _,i in sorted(rms,reverse=True)[:k]]+[i for _,i in sorted(pk,reverse=True)[:k]]))
  return [(i*sec,sec) for i in pick],sr
def excerpt_tp(raw,gain,wins,sr,tmp):
  worst=-120.0
  for s,d in wins:
    # 2 s pre-roll so the compressor/limiter settle as in the full master, measured on the whole excerpt (pre-roll included: conservative)
    a=max(0.0,s-2.0);y,_=sf.read(raw,start=int(a*sr),stop=int((s+d)*sr),dtype='float32',always_2d=True)
    w=os.path.join(tmp,'x_raw.wav');sf.write(w,y,sr,subtype='FLOAT')
    subprocess.run(['bash',MASTER,w,os.path.join(tmp,'x.mp3'),str(gain),os.path.join(tmp,'x_master.wav')],capture_output=True,text=True,check=True)
    worst=max(worst,tp_of(os.path.join(tmp,'x.mp3')))
  return worst
def full_master(raw,gain,mp3,master):
  subprocess.run(['bash',MASTER,raw,mp3,str(gain),master],capture_output=True,text=True,check=True);return tp_of(mp3)
def choose_gain_full(raw,start=9.0,floor=7.0,step=0.5,mp3=None,master=None,log=print):
  """exact: full master per step; leaves the passing master at mp3/master when given"""
  tried=[];g=start
  with tempfile.TemporaryDirectory() as tmp:
    while g>=floor-1e-9:
      m3=mp3 or os.path.join(tmp,'f.mp3');mw=master or os.path.join(tmp,'f_master.wav')
      tp=full_master(raw,g,m3,mw);tried.append((g,tp));log(f'gain {g:.1f}: full master true peak {tp:.2f} dBTP',flush=True)
      if tp<=TP_MAX:return dict(gain=g,tp=tp,tried=tried,method='full')
      g=round(g-step,3)
  return dict(gain=None,tried=tried,method='full')
def choose_gain(raw,start=9.0,floor=7.0,step=0.5,k=4,log=print):
  """excerpt shortcut (comparison only, see module doc)"""
  wins,sr=windows(raw,k);tried=[];g=start
  with tempfile.TemporaryDirectory() as tmp:
    while g>=floor-1e-9:
      tp=excerpt_tp(raw,g,wins,sr,tmp);tried.append((g,tp));log(f'gain {g:.1f}: worst excerpt true peak {tp:.2f} dBTP over {len(wins)} windows',flush=True)
      if tp<=TP_MAX:return dict(gain=g,tp_excerpt=tp,tried=tried,windows=wins)
      g=round(g-step,3)
  return dict(gain=None,tried=tried,windows=wins)
def full_tp(raw,gain):
  with tempfile.TemporaryDirectory() as tmp:
    subprocess.run(['bash',MASTER,raw,os.path.join(tmp,'f.mp3'),str(gain),os.path.join(tmp,'f_master.wav')],capture_output=True,text=True,check=True)
    return tp_of(os.path.join(tmp,'f.mp3'))
if __name__=='__main__':
  ap=argparse.ArgumentParser();ap.add_argument('raw');ap.add_argument('--start',type=float,default=9.0);ap.add_argument('--floor',type=float,default=7.0)
  ap.add_argument('--step',type=float,default=0.5);ap.add_argument('--excerpts',action='store_true');ap.add_argument('--json')
  ap.add_argument('--out-mp3');ap.add_argument('--out-master')
  A=ap.parse_args();import time;t0=time.time()
  R=choose_gain(A.raw,A.start,A.floor,A.step) if A.excerpts else choose_gain_full(A.raw,A.start,A.floor,A.step,A.out_mp3,A.out_master)
  R['secs']=round(time.time()-t0,1)
  print(json.dumps(R,default=float))
  if A.json:json.dump(R,open(A.json,'w'),indent=1,default=float)
  sys.exit(0 if R['gain'] is not None else 1)
