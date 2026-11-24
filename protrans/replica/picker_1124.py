#!/usr/bin/env python3
"""Nightly 2026-11-24 (copy of picker_1120 on the grown corpus): retrain the factored picker (picker_1119b: exit + cue LambdaMART rankers, X classifier, margin gate)
on the grown corpus_v2 (accepted count passed 150; ranker v0 used 82, picker_1119b used 148 dev).
Changes vs 1119b (code reused, not edited):
 - fresh snapshot of corpus_v2/accepted.jsonl into nightly_1124_work/ (EVERY mix listed in fresh_mixes.json is excluded
   from training and tagged 'fresh'; the locked holdout DJs Liquicity + Hospital Records stay out of dev);
 - majority-choice baseline (single exit tag x cue tag with lowest train error, fit leave-one-DJ-out);
 - per-pair decisions for every arm saved for failure analysis.
Primary arm is STYLE-FREE (the listener 2026-11-19 7:04 AM ET: stop predicting DJ style; it does not exist for his own mixes).
usage: picker_1120.py cv"""
import json, os, sys, collections, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); P0 = os.path.dirname(H); sys.path.insert(0, H)
import picker_1119 as P
W = os.path.join(H, 'nightly_1124_work'); os.makedirs(W, exist_ok=True)
FRESH_ALL = {m['mix_id'] for m in json.load(open(os.path.join(H, 'fresh_mixes.json')))['mixes']}
P.W = W; P.SPENT_FRESH = FRESH_ALL
snap = os.path.join(W, 'accepted_snapshot.jsonl')
if not os.path.exists(snap):
    with open(snap, 'w') as f:
        for l in open(os.path.join(P0, 'corpus_v2', 'accepted.jsonl')): f.write(l)
import picker_1119b as B
B.W = W

def tagpick(r, part, tag):
    return next((i for i, c in enumerate(r[part]) if tag in c['tags']), r[part + 'dix'])

def majority(tr, te):
    best = {}
    for part, tags in (('E', B.ETAGS), ('C', B.CTAGS)):
        errs = {t: np.mean([B.perr(r, part, tagpick(r, part, t)) for r in tr]) for t in tags if t != 'grid'}
        best[part] = min(errs, key=errs.get)
    Xs = collections.Counter(16 if (r['pro_ov'] or 0) <= 14 else 32 for r in tr).most_common(1)[0][0]
    return best, [B.decide(r, tagpick(r, 'E', best['E']), tagpick(r, 'C', best['C']), Xs) for r in te]

def run_cv(rows):
    from concurrent.futures import ProcessPoolExecutor
    dev = [r for r in rows if r['set'] == 'dev']; djs = sorted({r['dj'] for r in dev}); byid = {r['id']: r for r in dev}
    for st in (True, False): B.XM(dev, 'E', st); B.XM(dev, 'C', st)
    order = []; D = collections.defaultdict(list); folds = {}; maj = {}
    with ProcessPoolExecutor(max_workers=int(os.environ.get('CVW', 3))) as ex:
        for d, ids, res in ex.map(B._fold, [(d, dev) for d in djs]):
            te = [byid[i] for i in ids]; tr = [r for r in dev if r['dj'] != d]; order += te; folds[d] = {k: v['diag'] for k, v in res.items()}
            for nm in ('style', 'nostyle'):
                D[f'model_{nm}_gated'] += res[nm]['g']; D[f'model_{nm}_plain'] += res[nm]['p']
            D['default'] += [B.base_decisions(r, 'default') for r in te]; D['rule_drop_exit'] += [B.base_decisions(r, 'rule_drop_exit') for r in te]
            mb, md = majority(tr, te); maj[d] = mb; D['majority'] += md
    res = B.summarize(order, dict(D))
    return dict(n=len(order), n_mixes=len({r['mix'] for r in order}), n_djs=len(djs), def_src=dict(collections.Counter(r['def_src'] for r in order)),
                folds=folds, majority_tags=maj, results=res,
                per_pair=[dict(id=r['id'], dj=r['dj'], mix=r['mix'], pro_out=r['pro_out'], pro_in=r['pro_in'], pro_ov=r['pro_ov'], dex=r['dex'], dcue=r['dcue'], dX=r['dX'],
                               na=r['sa'].get('music_end'), **{k: D[k][i] for k in D}) for i, r in enumerate(order)])

if __name__ == '__main__':
    rows = B.build(P.rows_all(), P.load_rendered_defaults())
    print('sets', collections.Counter(r['set'] for r in rows), flush=True)
    out = run_cv(rows)
    json.dump(out, open(os.path.join(H, 'picker_1124_cv.json'), 'w'), indent=1, default=str)
    for n, s in out['results'].items():
        d = s.get('delta_vs_default', {}); g = lambda k: ((d.get(k) or {}).get('delta'), (d.get(k) or {}).get('ci'))
        print(f"{n:20s} ec {s['exit_cue_mean']} dEC {g('exit_cue')} dExit {g('exit')} dCue {g('cue')} e@4/8/16 {s['exit_hit4']}/{s['exit_hit8']}/{s['exit_hit16']} "
              f"c@4/8/16 {s['cue_hit4']}/{s['cue_hit8']}/{s['cue_hit16']} bl {s['blendlen_proxy_err_mean']} dbl {g('bl')} abstain {s['abstain_rate']}", flush=True)
