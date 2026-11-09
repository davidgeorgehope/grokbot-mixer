import os,sys,json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import diagnose_gap as D, score, paths
rows=json.load(open(os.path.join(paths.RESULTS,'admitted.json')))
ok=[]
for row in rows:
  try:
    paths_=[D._src_path(row[k]['yt']) for k in ('a','b')]
    pro_path=row.get('pro_clip') or os.path.join(paths.CLIPS,row['split'],row['id'],'pro.wav')
    if not all(os.path.isfile(p) for p in paths_+[pro_path]):
      print(row['id'],'missing_audio', flush=True); continue
    pro=D._load(pro_path); aligned=[]
    for side,path in zip(('a','b'),paths_):
      loc=(row.get('gate') or {}).get(side, {}).get('locate') or {}
      if loc.get('track_t') is None or loc.get('mix_t') is None:
        loc=D.version_match.locate_in(pro, score._load(path))
      if loc.get('track_t') is None:
        print(row['id'],'locate_failed',side, flush=True); raise RuntimeError('locate')
      a=D.place_source(path,loc['track_t'],loc['mix_t'],len(pro))
      a,_=D.refine_lag(pro,a); aligned.append(a)
    _,oracle,_,_=D.band_gains(pro,*aligned)
    p=score.source_gain_events(pro,*paths_)
    o=score.source_gain_events(oracle,*paths_)
    if p is None or o is None:
      print(row['id'],'events_none',p,o, flush=True); continue
    good=all(p[k] is not None and o[k] is not None and abs(p[k]-o[k])<=1 for k in ('bass_swap','outgoing_cut','blend_length'))
    print(row['id'], 'PASS' if good else 'fail', p, o, flush=True)
    if good: ok.append(row['id'])
  except Exception as e:
    print(row['id'],'error',type(e).__name__,e, flush=True)
print('OK',ok, flush=True)
json.dump(dict(ok=ok), open(os.path.join(paths.RESULTS,'oracle_scan.json'),'w'), indent=2)
