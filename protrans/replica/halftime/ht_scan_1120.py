import sys,json,os
sys.path.insert(0,'/workspace/mixes/protrans');sys.path.insert(0,'/workspace/mixes/protrans/replica/halftime')
import run_admitted_tune as T, halftime_tg as H, slowdown as S
out={}
for r in T.load_recs():
  for side in ('a','b'):
    yt=r[side]['yt']
    if yt in out: continue
    try:
      P=S.profile(yt); sec=json.load(open(f'/workspace/mixes/src2/st/{yt}.sections.json'))
      out[yt]=dict(title=r[side]['title'],slow=P and P['sections'],ht=H.sections(yt),secs=sec, ids=[r['id']])
    except Exception as e: out[yt]=dict(err=str(e))
    print(yt,out[yt].get('title'),'slow',out[yt].get('slow'),'ht',out[yt].get('ht'),'drops',(out[yt].get('secs') or {}).get('drops'),'end',(out[yt].get('secs') or {}).get('music_end'),flush=True)
json.dump(out,open('/workspace/mixes/protrans/results/ht_scan_1120.json','w'),indent=1)
