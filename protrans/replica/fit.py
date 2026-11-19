"""REPLICA v0: predict pro decisions per pair from track structure; leave-one-mix-out eval vs baselines."""
import json, os, sys, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decisions import load
R = load()
KEYS = sorted(R[0]['x'])
X = np.array([[r['x'][k] for k in KEYS] for r in R], float)
mixes = np.array([r['mix'] for r in R])
T = {k: np.array([r[k] for r in R], float) for k in ('out_left', 'in_rel_drop1', 'overlap')}

def default_rule(i):   # engine STRUCT outro->intro default: blend starts X=16 bars before music end, incoming drop lands at blend end
    return dict(out_left=16.0, in_rel_drop1=-16.0, overlap=16.0)

def median_model(tr):
    return lambda i: {k: float(np.median(T[k][tr])) for k in T}

def knn_model(tr, k=7):
    mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-6
    Z = (X - mu) / sd
    def f(i):
        d = np.linalg.norm(Z[tr] - Z[i], axis=1); nn = np.array(tr)[np.argsort(d)[:k]]
        return {kk: float(np.median(T[kk][nn])) for kk in T}
    return f

def gbm_model(tr):
    import lightgbm as lgb
    ms = {}
    for kk in T:
        m = lgb.LGBMRegressor(n_estimators=60, learning_rate=0.08, num_leaves=4, min_child_samples=6, objective='l1', seed=20261118, verbose=-1)
        m.fit(X[tr], T[kk][tr]); ms[kk] = m
    return lambda i: {kk: float(ms[kk].predict(X[i:i+1])[0]) for kk in T}

def style(out_left, in_rel):
    return ('outro' if out_left <= 40 else 'mid', 'intro' if in_rel < -4 else ('on_drop' if abs(in_rel) <= 4 else 'post_drop'))

def evaluate(builder):
    errs = {k: [] for k in T}; sty = []
    for m in sorted(set(mixes)):
        te = np.where(mixes == m)[0]; tr = np.where(mixes != m)[0]
        f = builder(list(tr))
        for i in te:
            p = f(i)
            for k in T: errs[k].append(abs(p[k] - T[k][i]))
            sty.append(style(p['out_left'], p['in_rel_drop1']) == style(T['out_left'][i], T['in_rel_drop1'][i]))
    out = {}
    for k in T:
        e = np.array(errs[k]); out[k] = dict(median_abs=round(float(np.median(e)), 1), within8=round(float(np.mean(e <= 8)), 3), within16=round(float(np.mean(e <= 16)), 3))
    both = np.array([(a <= 8 and b <= 8) for a, b in zip(errs['out_left'], errs['in_rel_drop1'])])
    out['cue_pair_within8'] = round(float(both.mean()), 3); out['style_match'] = round(float(np.mean(sty)), 3)
    return out

if __name__ == '__main__':
    res = dict(n=len(R), n_mixes=len(set(mixes)), features=KEYS,
               default_rule=evaluate(lambda tr: default_rule), median=evaluate(median_model),
               knn7=evaluate(lambda tr: knn_model(tr, 7)), knn11=evaluate(lambda tr: knn_model(tr, 11)), gbm=evaluate(gbm_model))
    print(json.dumps(res, indent=1))
    json.dump(res, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'eval_v0.json'), 'w'), indent=1)
