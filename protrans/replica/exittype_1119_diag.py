"""stage-1 diagnosis (dev LODO only): raw OOF AUC / log loss per model family and feature group"""
import exittype_1119 as T, picker_1119 as P, picker_1119b as B, json, collections, numpy as np
rows=B.build(P.rows_all(), P.load_rendered_defaults()); dev=[r for r in rows if r['set']=='dev']
fm={}
for l in open('nightly_1119_work/accepted_snapshot.jsonl'):
  a=json.loads(l); f=json.load(open('../corpus_v2/features/'+a['id']+'.json')); fm[a['id']]=(f['track_a']['yt'],f['track_b']['yt'])
by=collections.defaultdict(list)
for r in dev: r['ya'],r['yb']=fm[r['id']]; by[r['mix']].append(r)
for r in dev: r['past']=sorted([q for q in by[r['mix']] if q['idx']<r['idx']],key=lambda q:q['idx'])
y=np.array([T.is_mid(r) for r in dev]); djs=sorted({r['dj'] for r in dev})
def oof(kind, style):
  o=np.zeros(len(dev))
  for d in djs:
    a=[r for r in dev if r['dj']!=d]; ix=[i for i,r in enumerate(dev) if r['dj']==d]; o[ix]=T.fit_raw(a,style,kind)([dev[i] for i in ix])
  return o
for style in (True,False):
  for kind in ('lgb','logit','const'):
    o=oof(kind,style); print('style' if style else 'nostyle', kind, 'auc',round(T.auc(o,y),3),'ll',round(T.logloss(o,y),3),'acc@.5',round(np.mean((o>=.5)==y),3))
# missingness vs label/DJ
miss=np.array([np.isnan(T.FX(r,False)[18]) for r in dev])
print('curves missing rate', miss.mean().round(3), 'mid rate when missing', y[miss].mean().round(3), 'when present', y[~miss].mean().round(3))
print('missing by dj', {d: round(float(np.mean([m for m,r in zip(miss,dev) if r['dj']==d])),2) for d in djs})
print('mid rate by dj', {d: round(float(np.mean([t for t,r in zip(y,dev) if r['dj']==d])),2) for d in djs})

rmiss=np.array([np.isnan(T.FX(r,False)[26]) for r in dev]); print('roughness missing', rmiss.mean().round(3), 'mid|miss', y[rmiss].mean().round(3), 'mid|present', y[~rmiss].mean().round(3))
print('rough missing by dj', {d: round(float(np.mean([m for m,r in zip(rmiss,dev) if r['dj']==d])),2) for d in djs})
import os
print('pairs with both st wavs', np.mean([os.path.exists('/workspace/mixes/src2/st/%s.wav'%r['ya']) and os.path.exists('/workspace/mixes/src2/st/%s.wav'%r['yb']) for r in dev]).round(3))
