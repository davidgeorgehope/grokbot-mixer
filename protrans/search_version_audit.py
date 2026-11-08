"""Check downloaded studio candidates against the pro outside the overlap."""
import os,json
import diagnose_gap as D
import version_match as V
CASES={'15':('a',['DpYdXERlkFk','cb2sbJ-ii-I']), '16':('b',['0KOtkN6iLkA','lgJT58nMECs']), '24':('b',['KD5fLb-WgBU'])}
rows=json.load(open(os.path.join(D.paths.RESULTS,'admitted_before_version_audit.json')));out=[]
for suffix,(side,ids) in CASES.items():
 row=next(r for r in rows if r['id']=='netsky_hospital_classics__'+suffix)
 pro=D._load(row['pro_clip']);n=len(pro)
 diag=next(r for r in json.load(open(D.OUT_JSON))['clips'] if r['id']==row['id'])
 region=diag['version']['solo_window_'+side]
 for yt in ids:
  p=f'/workspace/mixes/protrans/cache/version_search/{yt}.webm'
  if not os.path.isfile(p):continue
  source=D._load(p)
  hits,_=V.CC.locate(V.CC.bandpow(pro),V.CC.bandpow(source),chunk_s=6.,hop_s=3.)
  candidates=[]
  for hit in sorted(hits,key=lambda h:-h[2])[:12]:
   loc0=dict(track_t=float(hit[0]),mix_t=float(hit[1]),cc=float(hit[2]),z=float(hit[3]))
   a=D.place_source(p,loc0['track_t'],loc0['mix_t'],n)
   a,_=D.refine_lag(pro,a,max_s=.9)
   sl=slice(int(region[0]*D.SR),int(region[1]*D.SR))
   candidates.append((D.spec_corr(pro[sl],a[sl]),loc0))
  if not candidates:continue
  loc=max(candidates,key=lambda x:x[0])[1]
  if loc['track_t'] is None:continue
  rate,best,c0=D.search_rate(pro,p,loc['track_t'],loc['mix_t'],n,region)
  placed=D.place_source(p,loc['track_t'],loc['mix_t'],n,rate=rate)
  placed,lag=D.refine_lag(pro,placed,max_s=.9)
  sl=slice(int(region[0]*D.SR),int(region[1]*D.SR))
  corr=D.spec_corr(pro[sl],placed[sl])
  r=dict(id=row['id'],side=side,yt=yt,url='https://www.youtube.com/watch?v='+yt,locate=loc,rate=rate,region=region,correlation=round(corr,4),pass_match=corr>=.70)
  out.append(r);print(r,flush=True)
  with open('/workspace/mixes/protrans/results/version_search_audit.json','w') as f:json.dump(out,f,indent=2)
