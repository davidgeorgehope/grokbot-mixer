import json,numpy as np,collections
d=json.load(open('picker_1124_cv.json')); pp=d['per_pair']
arms=['default','majority','model_nostyle_gated','model_nostyle_plain','model_style_gated']
def ex(r,a): return abs(r[a]['exit']-r['pro_out'])
def cu(r,a): return abs(r[a]['cue']-r['pro_in'])
def ec(r,a): return (ex(r,a)+cu(r,a))/2
def bl(r,a): return abs(r[a]['X']-(16 if (r['pro_ov'] or 0)<=14 else 32))
mixes=sorted({r['mix'] for r in pp}); idx=collections.defaultdict(list)
for i,r in enumerate(pp): idx[r['mix']].append(i)
rng=np.random.default_rng(20261124); B=4000
def boot(f,a,b):
    A=np.array([f(r,a)-f(r,b) for r in pp]); 
    sums=[]
    for _ in range(B):
        ms=rng.choice(len(mixes),len(mixes)); ii=np.concatenate([idx[mixes[m]] for m in ms]); sums.append(A[ii].mean())
    return round(float(A.mean()),2),[round(float(np.percentile(sums,2.5)),2),round(float(np.percentile(sums,97.5)),2)]
out={}
for a in ['model_nostyle_gated','model_nostyle_plain']:
  for ref in ['default','majority']:
    out[f'{a}_vs_{ref}']={m:boot(f,a,ref) for m,f in (('exit_cue',ec),('exit',ex),('cue',cu),('blendlen',bl))}
    for t in (4,8,16):
        for nm,f in (('exit',ex),('cue',cu)):
            g=lambda r,x,f=f,t=t:-float(f(r,x)<=t)  # negative hit => lower is better
            m,ci=boot(g,a,ref); out[f'{a}_vs_{ref}'][f'{nm}_hit{t}_gain']=(-m,[-ci[1],-ci[0]])
# gate coverage
for a in ['model_nostyle_gated','model_nostyle_plain']:
    out[a+'_abstain']=round(float(np.mean([r[a]['is_default'] for r in pp])),3)
# mid vs late
late=[r for r in pp if r['pro_out']>=r['na']-40]; mid=[r for r in pp if r['pro_out']<r['na']-40]
out['strata']={'n_mid':len(mid),'n_late':len(late)}
for nm,S in (('mid',mid),('late',late)):
    out['strata'][nm]={a:round(float(np.mean([ex(r,a) for r in S])),1) for a in arms}
# per DJ delta nostyle gated vs default
dj=collections.defaultdict(list)
for r in pp: dj[r['dj']].append(ec(r,'model_nostyle_gated')-ec(r,'default'))
pd={k:(round(float(np.mean(v)),1),len(v)) for k,v in dj.items()}
out['per_dj_worst']=sorted(pd.items(),key=lambda x:-x[1][0])[:6]; out['per_dj_best']=sorted(pd.items(),key=lambda x:x[1][0])[:4]
out['djs_worse']=sum(1 for v in pd.values() if v[0]>0); out['n_djs']=len(pd)
w=sorted(pp,key=lambda r:-(ec(r,'model_nostyle_gated')-ec(r,'default')))[:6]
out['worst_pairs']=[(r['id'],round(ec(r,'model_nostyle_gated')-ec(r,'default'),1),round(r['pro_out']),r['na'],r['model_nostyle_gated']['exit']) for r in w]
# breakdown-ish exit share: model exit tag unavailable; share of mid-track picks
out['model_midtrack_pick_share']=round(float(np.mean([r['model_nostyle_gated']['exit']<r['na']-40 for r in pp])),3)
out['default_midtrack_share']=round(float(np.mean([r['default']['exit']<r['na']-40 for r in pp])),3)
out['pro_midtrack_share']=round(float(np.mean([r['pro_out']<r['na']-40 for r in pp])),3)
json.dump(out,open('picker_1124_analysis.json','w'),indent=1)
print(json.dumps(out,indent=1))

# --- cue-only hybrid (post-hoc idea tested after seeing exit CI include 0): default exit + default X, model cue
for r in pp:
    for a in ('model_nostyle_gated','model_nostyle_plain'):
        r[a+'_cueonly']={'exit':r['default']['exit'],'cue':r[a]['cue'],'X':r['default']['X']}
h={}
for a in ('model_nostyle_gated_cueonly','model_nostyle_plain_cueonly'):
    for ref in ('default','majority'):
        h[f'{a}_vs_{ref}']={m:boot(f,a,ref) for m,f in (('exit_cue',ec),('exit',ex),('cue',cu),('blendlen',bl))}
json.dump(h,open('picker_1124_cueonly.json','w'),indent=1); print(json.dumps(h))
