"""n1125 post-hoc (does NOT count): ride-vs-leave classifier feature sets, leave-one-DJ-out AUC on dev."""
import sys, os, json, numpy as np, collections
sys.path.insert(0, '.')
import picker_1119 as P
P.W = 'nightly_1125_work'; P.SPENT_FRESH = {m['mix_id'] for m in json.load(open('fresh_mixes.json'))['mixes']}
import picker_1119b as B, lightgbm as lgb
from sklearn.metrics import roc_auc_score
rows = [r for r in B.build(P.rows_all(), P.load_rendered_defaults()) if r['set'] == 'dev']
na = lambda s: float(s.get('music_end') or s.get('n_bars'))
def sec(s, k, f): return ((s.get('bass_by_section') or {}).get(k) or {}).get(f, np.nan)
def fB(r):
    sa, sb = r['sa'], r['sb']; dr = sa.get('drops') or [[0, 0]]
    return B.base_feats(r) + [na(sa) - dr[-1][1], na(sa) - dr[0][1], dr[-1][1] - dr[-1][0], sec(sa, 'outro', 'energy') - sec(sa, 'drop', 'energy'), sec(sa, 'outro', 'drums') - sec(sa, 'drop', 'drums'),
        sec(sa, 'outro', 'bass') - sec(sa, 'drop', 'bass'), sec(sb, 'intro', 'energy') - sec(sb, 'drop', 'energy'), sec(sb, 'intro', 'drums'), (sb.get('drop1') or 0), na(sb), r['idx'],
        (r['bpm'][0] or np.nan)]
def fC(r):
    h = r['hist']; return fB(r) + ([h['n'], h['mid'], h['left'], h['ov']] if h else [0, np.nan, np.nan, np.nan])
y = np.array([float(na(r['sa']) - r['pro_out'] > 40) for r in rows]); djs = sorted({r['dj'] for r in rows}); out = {}
for nm, F in (('A_current', lambda r: B.base_feats(r) + [len(r['sa'].get('drops') or []) and na(r['sa']) - r['sa']['drops'][-1][1]]), ('B_rich_pair', fB), ('C_rich_plus_online_mix_history', fC)):
    X = np.array([F(r) for r in rows], float); p = np.zeros(len(rows))
    for d in djs:
        tr = np.array([r['dj'] != d for r in rows])
        m = lgb.LGBMClassifier(n_estimators=150, num_leaves=7, learning_rate=0.05, min_child_samples=15, subsample=0.8, subsample_freq=1, verbose=-1, n_jobs=2, random_state=1).fit(X[tr], y[tr])
        p[~tr] = m.predict_proba(X[~tr])[:, 1]
    out[nm] = round(float(roc_auc_score(y, p)), 3); print(nm, out[nm], flush=True)
json.dump(out, open('nightly_1125_work/ride_explore.json', 'w'))
