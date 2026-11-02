"""How pro liquid sets handle beats -> melody-only (the listener 2026-11-02). For each detected transition in eval/sets/<set>.json,
decode the set around it, split percussive/harmonic (HPSS), per-bar dB on the set's bar grid. Classify the drum behaviour
across the transition window [start-8 bars, end+16 bars]:
  drop_cut      percussive falls >=10 dB within <=1 bar while harmonic stays within 6 dB (beat cut into melody: family A)
  drop_fast     same over 2 bars
  fade_mushy    percussive falls >=10 dB over >=4 bars with harmonic held (the slow beat fade the listener dislikes)
  melody_cross  >=4 consecutive bars with percussive >=12 dB under the set median while harmonic is held (melodies crossing, no beat: family B)
  continuous    beat never drops >=10 dB (beat carried through: beat cross / loop, family C or plain beat-to-beat)
Cut timing: drop bar relative to the transition start bar (mod 4 / mod 8) and to the detected swap bar.
Writes eval/pro_beatmelody.json. Indications only (HPSS on a full mix; n small)."""
import json,subprocess,sys,numpy as np,librosa,os
R='/workspace/mixes';OUT=f'{R}/eval/pro_beatmelody.json';SR=22050
def load(path,t0,dur):
  b=subprocess.run(['ffmpeg','-v','quiet','-ss',str(max(0,t0)),'-t',str(dur),'-i',path,'-ac','1','-ar',str(SR),'-f','f32le','-'],capture_output=True).stdout
  return np.frombuffer(b,np.float32)
res=[]
for s in ['hospital_podcast393','wilkinson_boomtown2026','dimension_allstars360','wilkinson_oldguard']:
  d=json.load(open(f'{R}/eval/sets/{s}.json'));bar=240/d['bpm'];path=f'{R}/pro_sets/{s}.m4a'
  for k,t in enumerate(d['transitions']):
    w0=t['start_sec']-8*bar;n=int((t['end_sec']-t['start_sec'])/bar)+24;y=load(path,w0,n*bar)
    if len(y)<SR*bar*8:continue
    H,P=librosa.effects.hpss(y);L=int(bar*SR);nb=len(y)//L
    db=lambda z:np.array([10*np.log10(np.mean(z[i*L:(i+1)*L]**2)+1e-12) for i in range(nb)])
    p,h=db(P),db(H);pm,hm=np.median(p),np.median(h);ob=int(round((t['end_sec']-t['start_sec'])/bar))
    cls='continuous';cut=None
    for i in range(1,nb):
      for span,c in ((1,'drop_cut'),(2,'drop_fast')):
        if i-span>=0 and p[i-span]>pm-4 and p[i]<p[i-span]-10 and abs(h[i]-h[i-span])<6 and cls=='continuous':cls,cut=c,i
    if cls=='continuous':
      for i in range(4,nb):
        if p[i-4]>pm-4 and p[i]<p[i-4]-10 and all(np.diff(p[i-4:i+1])>-10) and h[i]>h[i-4]-6:cls,cut='fade_mushy',i;break
    low=(p<pm-12)&(h>hm-6);run=mx=0
    for v in low:run=run+1 if v else 0;mx=max(mx,run)
    if cls=='continuous' and mx>=4:cls='melody_cross'
    rel=None if cut is None else cut-8
    res.append(dict(set=s,i=k,t=f"{int(t['start_sec']//60)}:{int(t['start_sec']%60):02d}",sec=round(t['start_sec'],1),overlap_bars=t['overlap_bars'],cls=cls,cut_rel_start=rel,
      cut_mod4=None if rel is None else rel%4,cut_rel_swap=None if cut is None else round(cut-8-(t['swap_sec']-t['start_sec'])/bar,1),beatless_run=int(mx)))
    print(res[-1],flush=True)
from collections import Counter
cuts=[r for r in res if r['cut_rel_start'] is not None]
summ=dict(n=len(res),by_cls=dict(Counter(r['cls'] for r in res)),cut_mod4=dict(Counter(r['cut_mod4'] for r in cuts)),
  cut_rel_swap_median=float(np.median([r['cut_rel_swap'] for r in cuts])) if cuts else None,
  cut_rel_swap=sorted(r['cut_rel_swap'] for r in cuts))
json.dump(dict(doc=__doc__,summary=summ,rows=res),open(OUT,'w'),indent=1);print(json.dumps(summ))
