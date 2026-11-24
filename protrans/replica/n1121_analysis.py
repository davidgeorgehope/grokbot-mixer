"""n1121 post-analysis (read-only): per arm, vetoes (render veto fired + replaced), gray, and share of blends that START in a breakdown, vs default."""
import sys, json, os
sys.path.insert(0,'/workspace/mixes/protrans')
import run_admitted_tune as T, provsours as P
recs={r['id']:r for r in T.load_recs()}
def sect(rid,win):
    rec=recs[rid]; ya=rec['a']['yt']; _,ea,_,ib,X=win
    return P.label(ya,ea-X).split(' +')[0]
out={}
arms=['base','epg_strict','epg_drop','epg_stack','dclash_land6','dclash_land7']
for a in arms:
    h=T.load_ckpt(f'n1121_{a}')
    secs={}; veto=[]; gray=[]; land=[]
    for rid,r in h.items():
        if r.get('error') or not r.get('pick'): continue
        secs[rid]=sect(rid,r['pick']['win'])
        d=r.get('drumclash') or {}
        hd=d.get('hard') or {}
        if hd.get('flagged'): veto.append(dict(id=rid,level=hd.get('level'),conf=hd.get('confidence'),replaced=bool(hd.get('replaced_by')),fallback=hd.get('fallback'),to=(hd.get('replaced_by') or {}).get('fam')))
        if d.get('gray'): gray.append(rid)
        if d.get('landing_pick'): land.append(rid)
    n=len(secs); bd=sum(1 for v in secs.values() if v=='breakdown')
    out[a]=dict(n=n,breakdown_start=bd,share=round(bd/max(n,1),3),sections={k:sum(1 for v in secs.values() if v==k) for k in set(secs.values())},vetoed=len(veto),vetoes=veto,gray=gray,landing_pick=land,secs=secs)
json.dump(out,open('/workspace/mixes/protrans/replica/n1121_analysis.json','w'),indent=1)
for a,v in out.items(): print(a,'n',v['n'],'breakdown-start',v['breakdown_start'],v['share'],v['sections'],'vetoed',v['vetoed'],'gray',len(v['gray']))
