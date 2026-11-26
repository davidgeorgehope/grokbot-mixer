#!/usr/bin/env python3
"""n1126 iteration (POST-HOC, does not count toward promotion): 'ridegate_conf' = ridegate whose exit move is applied only when a
calibrated "will this beat the default exit?" classifier says P >= 0.5 (no threshold tuning). The classifier is fit on the TRAINING
rows' inner leave-one-DJ-out picks (picks the model would have made on them without seeing them), features = ride probability,
ranker margin over the default, track length, bars left after the move, mid-track flag, drop count; label = the move's exit error is
lower than the default's. Cue as ridegate (gated cue ranker). Same data/folds as picker_1126 cv. usage: picker_1126b.py cv"""
import json, os, sys, collections, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import picker_1126 as N
Q, P, B = N.Q, N.P, N.B
import lightgbm as lgb

def cf(r, j, s, p):
    v = r['E'][j]['v']; na = Q.na_(r)
    return [p, float(s[j] - s[r['Edix']]), na, na - v, float(Q.is_mid(r, v)), len(r['sa'].get('drops') or []), v - r['dex']]

def train_predict(tr, te):
    djs = sorted({r['dj'] for r in tr}); P_in = {}
    for d in djs:
        a = [r for r in tr if r['dj'] != d]; b = [r for r in tr if r['dj'] == d]
        for r, p in zip(b, Q.fit_ride(a)(b)): P_in[r['id']] = p
    ride = Q.fit_ride(tr)(te)
    (eE, ciE, tauE), S_in = Q.inner_oof(tr, 'E'); th = Q.choose_theta(tr, S_in, tauE, P_in)[1]
    X, y = [], []
    for r in tr:
        j = Q.ride_pick(r, B.gpick(r, 'E', S_in[r['id']], tauE), P_in[r['id']], th)
        if j == r['Edix']: continue
        X.append(cf(r, j, S_in[r['id']], P_in[r['id']])); y.append(float(B.perr(r, 'E', j) < B.perr(r, 'E', r['Edix'])))
    clf = lgb.LGBMClassifier(n_estimators=150, num_leaves=7, learning_rate=0.05, min_child_samples=15, subsample=0.8, subsample_freq=1, verbose=-1, n_jobs=1, random_state=N.SEED).fit(np.array(X, float), np.array(y))
    mE = B.fit(tr, 'E', False, B.CFGS[ciE]); SE = B.scores(mE, te, 'E', False)
    jr = [Q.ride_pick(r, B.gpick(r, 'E', s, tauE), p, th) for r, s, p in zip(te, SE, ride)]
    pc = [float(clf.predict_proba(np.array([cf(r, j, s, p)], float))[0, 1]) if j != r['Edix'] else None for r, j, s, p in zip(te, jr, SE, ride)]
    jconf = [j if (q is not None and q >= 0.5) else r['Edix'] for r, j, q in zip(te, jr, pc)]
    eC, ciC, tauC = B.inner(tr, 'C', False); mC = B.fit(tr, 'C', False, B.CFGS[ciC]); SC = B.scores(mC, te, 'C', False)
    jc = [B.gpick(r, 'C', s, tauC) for r, s in zip(te, SC)]
    D = dict(ridegate=[B.decide(r, j, c, r['dX']) for r, j, c in zip(te, jr, jc)], ridegate_conf=[B.decide(r, j, c, r['dX']) for r, j, c in zip(te, jconf, jc)],
             default=[B.base_decisions(r, 'default') for r in te])
    mb, md = Q.majority(tr, te); D['majority'] = md
    for k in D:
        for x, p, q in zip(D[k], ride, pc): x['p_leave'] = round(float(p), 3); x['p_leave_tf'] = None; x['p_beat'] = q
    return D, dict(tau=tauE, theta=th, n_conf_train=len(y), conf_pos_rate=round(float(np.mean(y)), 3) if y else None)

def _fold(args):
    d, dev = args; tr = [r for r in dev if r['dj'] != d]; te = [r for r in dev if r['dj'] == d]
    D, diag = train_predict(tr, te); print('fold', d, len(te), diag, flush=True); return d, [r['id'] for r in te], D, diag

if __name__ == '__main__':
    rows = B.build(P.rows_all(), P.load_rendered_defaults())
    for r in rows:
        if r['dj'] in N.EXCL_DJ and r['set'] == 'dev': r['set'] = 'excluded'
    dev = [r for r in rows if r['set'] == 'dev']; B.XM(dev, 'E', False); B.XM(dev, 'C', False); print('dev', len(dev), flush=True)
    from concurrent.futures import ProcessPoolExecutor
    djs = sorted({r['dj'] for r in dev}); byid = {r['id']: r for r in dev}; order = []; D = collections.defaultdict(list); folds = {}
    with ProcessPoolExecutor(max_workers=int(os.environ.get('CVW', 3))) as ex:
        for d, ids, Dd, diag in ex.map(_fold, [(d, dev) for d in djs]):
            order += [byid[i] for i in ids]; folds[d] = diag
            for k, v in Dd.items(): D[k] += v
    pp = N.pp_rows(order, D)
    for i, x in enumerate(pp): x['p_beat'] = D['ridegate_conf'][i].get('p_beat')
    json.dump(dict(n=len(order), folds=folds, per_pair=pp), open(os.path.join(N.W, 'picker_1126b_cv.json'), 'w'), indent=1, default=str)
    print('DONE', flush=True)
