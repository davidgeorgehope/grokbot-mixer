"""Report-only pro-likeness per blend (not pass/fail). For each blend: out = cue.pctl of where the outgoing record ends,
1 = where Raveform pros would end it; len = how typical the blend
length is for real DnB (median 26 bars). Score = mean of the two, or the listener's fitted weights once he has rated blends.
usage: cue_report.py META.json [--json OUT]        fine-tune: cue_report.py --fit ../eval/blend_ratings.jsonl
ratings jsonl rows: {"mix":"<meta name>","t":"mm:ss","rating":1-5}"""
import json,sys,os,numpy as np
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)));import cue
from engine import track
M=cue.load()
def blends(meta):
  D={d['id']:d for d in meta['decks']};bar=meta['bar_sec'];out=[]
  for t in meta['trans']:
    a,b=D[t['a']],D[t['b']];X={}
    for x in(a,):
      if x['id'] not in X:g=track(x['id'])['g']['bar'];X[x['id']]=cue.track_feats(g['all'],g['low'],g['hat'])
    po=cue.pctl(M,'out',X[a['id']],max(s for s,_ in a['full_map'])+1)
    n=t['end_bar']-t['start_bar'];pl=float(np.clip(1-abs(np.log2(max(n,1)/26))/2,0,1));f=[po,pl]
    rf=M.get('rating_fit');s=float(np.clip((np.dot(rf['w'],f)+rf['b']-1)/4,0,1)) if rf else float(np.mean(f))
    s0=t['start_bar']*bar;out.append(dict(t=f'{int(s0//60)}:{int(s0%60):02d}',a=t['a'],b=t['b'],bars=n,out=round(po,2),len=round(pl,2),score=round(s,2)))
  return out
if sys.argv[1]=='--fit':
  rows=[json.loads(l) for l in open(sys.argv[2])];F=[];y=[]
  for r in rows:
    mp=f"{r['mix']}_meta.json";bl={b['t']:b for b in blends(json.load(open(mp)))} if os.path.exists(mp) else {}
    if r['t'] in bl:b=bl[r['t']];F.append([b['out'],b['len']]);y.append(float(r['rating']))
  if len(y)<8:sys.exit(f'{len(y)} matched ratings; need >= 8 before fitting')
  A=np.c_[np.array(F),np.ones(len(y))];w=np.linalg.solve(A.T@A+np.diag([1,1,0]),A.T@np.array(y))  # ridge, intercept unpenalised
  M['rating_fit']=dict(w=w[:2].round(4).tolist(),b=round(float(w[2]),4),n=len(y));json.dump(M,open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'cue_model.json'),'w'),indent=0)
  print('fitted on',len(y),'ratings:',M['rating_fit']);sys.exit()
B=blends(json.load(open(sys.argv[1])))
print(f"PRO-LIKENESS (report only) mean {np.mean([b['score'] for b in B]):.2f} over {len(B)} blends; lowest:")
for b in sorted(B,key=lambda b:b['score'])[:5]:print(f"  {b['t']} {b['a']}->{b['b']} score {b['score']} (out {b['out']}, len {b['bars']} bars)")
if '--json' in sys.argv:json.dump(B,open(sys.argv[sys.argv.index('--json')+1],'w'),indent=1)
