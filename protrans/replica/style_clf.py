"""REPLICA v0b: predict the pro's coarse technique (exit mid-track vs play outro; incoming from intro vs on/after its drop) per pair."""
import json, os, sys, numpy as np
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decisions import load
R = load(); KEYS = sorted(R[0]['x'])
X = np.array([[r['x'][k] for k in KEYS] for r in R], float); mixes = np.array([r['mix'] for r in R])
y_out = np.array([r['out_style'] == 'mid' for r in R], int)
y_in = np.array([r['in_style'] != 'intro' for r in R], int)
y_ov = np.array([(r['overlap'] or 0) >= 24 for r in R], int)

def lomo(y, kind):
    from sklearn.linear_model import LogisticRegression
    import lightgbm as lgb
    pred = np.zeros(len(y)); 
    for m in sorted(set(mixes)):
        te = mixes == m; tr = ~te
        if kind == 'majority': pred[te] = float(y[tr].mean() >= 0.5)
        elif kind == 'logreg':
            mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-6
            c = LogisticRegression(C=0.3, max_iter=2000).fit((X[tr]-mu)/sd, y[tr]); pred[te] = c.predict((X[te]-mu)/sd)
        elif kind == 'gbm':
            c = lgb.LGBMClassifier(n_estimators=60, learning_rate=0.08, num_leaves=4, min_child_samples=6, random_state=20261118, verbose=-1).fit(X[tr], y[tr]); pred[te] = c.predict(X[te])
    return round(float((pred == y).mean()), 3)

if __name__ == '__main__':
    out = dict(n=len(R), base_rates=dict(out_mid=round(y_out.mean(),3), in_drop_anchored=round(y_in.mean(),3), overlap_ge24=round(y_ov.mean(),3)))
    for name, y in (('out_mid', y_out), ('in_drop_anchored', y_in), ('overlap_ge24', y_ov)):
        out[name] = {k: lomo(y, k) for k in ('majority', 'logreg', 'gbm')}
    by = defaultdict(list)
    for r in R: by[r['dj']].append(r)
    out['by_dj'] = {dj: dict(n=len(v), out_mid=round(np.mean([x['out_style']=='mid' for x in v]),2), in_drop=round(np.mean([x['in_style']!='intro' for x in v]),2), overlap_med=round(float(np.median([x['overlap'] or 0 for x in v])),1)) for dj, v in sorted(by.items(), key=lambda kv: -len(kv[1]))}
    print(json.dumps(out, indent=1)); json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'eval_v0b_style.json'), 'w'), indent=1)
