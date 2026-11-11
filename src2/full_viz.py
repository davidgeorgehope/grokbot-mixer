"""Full-mix staff_viz --v1plus: one 2-deck segment per transition (timing.json like bm_demo), frame-aligned boundaries, concat + full audio."""
# NOTE 2026-11-11: this per-transition cut (midpoint between blends, decks=[out, in] by ROLE) is the shared root of the
# "deck swaps after a blend" bug in both the score visual and the turntable visual: at each cut the track that came in
# on the IN/right lane is redrawn on the OUT/left lane. The turntable copy (visuals/code/turntable_viz/build_segs.py) now
# uses deck_state.py (physical decks, track k on deck k % 2). This retired score visual is left as is.
import json,os,sys,copy,math,subprocess,numpy as np
os.environ['NUDGE']='/nonexistent'  # m06v2/v3 render nudge (none)
import engine as E
M=json.load(open(sys.argv[1]));MP3=sys.argv[2];OUT=sys.argv[3];FPS=25;BAR=M['bar_sec'];T=M['trans'];D=M['decks']
fa=lambda b:round(b*BAR*FPS)/FPS  # frame-aligned seconds
cut=[0.0]+[fa((T[i-1]['end_bar']+T[i]['start_bar'])/2) for i in range(1,len(T))]+[math.floor(M['len_sec']*FPS)/FPS]
segs=[]
for i,t in enumerate(T):
  t0,t1=cut[i],cut[i+1];s0=t0/BAR;s1=t1/BAR;tag=f'seg{i:02d}';clip=f'{OUT}/{tag}.wav'
  subprocess.run(['ffmpeg','-loglevel','error','-y','-ss',f'{t0:.4f}','-t',f'{t1-t0:.4f}','-i',MP3,'-ar','44100',clip],check=True)
  tim=dict(clip=clip,sr=E.SR,bs=E.BS,bar_sec=BAR,clip_start_bar=s0,clip_end_bar=s1,nudge='/nonexistent',trans_index=i,trans=t,decks=[],
    events=[dict(kind=k,deck=d['id'],mix_bar=d['start_bar']+d[k]['k0'] if k=='ib' else d[k]['bar'],end_bar=d['start_bar']+d[k]['k1'] if k=='ib' else d[k]['bar']+d[k]['xf'],params=d[k]) for d in D[i:i+2] for k in ('ib','dswap') if d.get(k)])
  for d in D[i:i+2]:
    j0=max(0,int(math.floor(s0))-d['start_bar']);j1=min(len(d['full_map']),int(math.ceil(s1))+1-d['start_bar'])
    dd=copy.deepcopy(d);dd['full_map']=d['full_map'][j0:j1];dd['start_bar']=d['start_bar']+j0
    if dd.get('ib'):dd['ib']=dict(dd['ib'],k0=max(0,dd['ib']['k0']-j0),k1=dd['ib']['k1']-j0)
    dd.pop('echo_out',None);tim['decks'].append(dd)
  json.dump(tim,open(f'{OUT}/{tag}.timing.json','w'),default=float);segs.append((tag,t1-t0))
json.dump(segs,open(f'{OUT}/segs.json','w'));print(len(segs),'segments',cut[-1])
