"""n1125 analysis of picker_1125_cv.json: grouped bootstrap by mix (4000, seed 20261125) for every arm vs default and vs majority."""
import json, numpy as np, collections, os
H = os.path.dirname(os.path.abspath(__file__))
d = json.load(open(os.path.join(H, 'picker_1125_cv.json'))); pp = d['per_pair']
ARMS = ['cueonly_gated', 'ridegate', 'ridegate_cand2', 'ref_full_gated', 'ref_full_plain', 'ref_cand2_full_gated', 'majority', 'rule_drop_exit']
ex = lambda r, a: abs(r[a]['exit'] - r['pro_out']); cu = lambda r, a: abs(r[a]['cue'] - r['pro_in'])
ec = lambda r, a: (ex(r, a) + cu(r, a)) / 2
OV = {16: 10.0, 32: 18.0}
bl = lambda r, a: abs(OV.get(r[a]['X'], 10.0) - (r['pro_ov'] if r['pro_ov'] is not None else 10.0))
mixes = sorted({r['mix'] for r in pp}); idx = collections.defaultdict(list)
for i, r in enumerate(pp): idx[r['mix']].append(i)
rng = np.random.default_rng(20261125); NB = 4000
BS = [np.concatenate([idx[mixes[m]] for m in rng.choice(len(mixes), len(mixes))]) for _ in range(NB)]
def boot(f, a, b):
    A = np.array([f(r, a) - f(r, b) for r in pp]); s = [A[ii].mean() for ii in BS]
    return [round(float(A.mean()), 2), round(float(np.percentile(s, 2.5)), 2), round(float(np.percentile(s, 97.5)), 2)]
out = dict(n=len(pp), n_mixes=len(mixes), n_djs=d['n_djs'], means={}, hits={}, deltas={})
for a in ['default'] + ARMS:
    out['means'][a] = dict(exit_cue=round(float(np.mean([ec(r, a) for r in pp])), 2), exit=round(float(np.mean([ex(r, a) for r in pp])), 2),
                           cue=round(float(np.mean([cu(r, a) for r in pp])), 2), blendlen=round(float(np.mean([bl(r, a) for r in pp])), 2),
                           abstain=round(float(np.mean([r[a]['is_default'] for r in pp])), 3),
                           exit_moved=round(float(np.mean([r[a]['exit'] != r['default']['exit'] for r in pp])), 3),
                           cue_moved=round(float(np.mean([r[a]['cue'] != r['default']['cue'] for r in pp])), 3),
                           midtrack_exit_share=round(float(np.mean([r[a]['exit'] < r['na'] - 40 for r in pp])), 3))
    out['hits'][a] = {f'{k}@{t}': round(float(np.mean([f(r, a) <= t for r in pp])), 3) for k, f in (('exit', ex), ('cue', cu)) for t in (4, 8, 16)}
for a in ARMS:
    for ref in ('default', 'majority'):
        if a == ref: continue
        D = {m: boot(f, a, ref) for m, f in (('exit_cue', ec), ('exit', ex), ('cue', cu), ('blendlen', bl))}
        for t in (4, 8, 16):
            for nm, f in (('exit', ex), ('cue', cu)):
                m, lo, hi = boot(lambda r, x, f=f, t=t: -float(f(r, x) <= t), a, ref); D[f'{nm}_hit{t}_gain'] = [-m, -hi, -lo]
        out['deltas'][f'{a}_vs_{ref}'] = D
late = [r for r in pp if r['pro_out'] >= r['na'] - 40]; mid = [r for r in pp if r['pro_out'] < r['na'] - 40]
out['strata'] = dict(n_mid=len(mid), n_late=len(late), exit_err={nm: {a: round(float(np.mean([ex(r, a) for r in S])), 1) for a in ['default'] + ARMS} for nm, S in (('pro_mid', mid), ('pro_late', late))})
# ride classifier quality (out-of-fold, p_leave is computed in the test fold)
y = np.array([r['pro_out'] < r['na'] - 40 for r in pp]); p = np.array([r['default']['p_leave'] for r in pp])
try:
    from sklearn.metrics import roc_auc_score; out['ride_auc'] = round(float(roc_auc_score(y, p)), 3)
except Exception: pass
out['ride_calib'] = {f'{lo:.1f}-{lo+0.2:.1f}': [int(((p >= lo) & (p < lo + 0.2)).sum()), round(float(y[(p >= lo) & (p < lo + 0.2)].mean()), 2) if ((p >= lo) & (p < lo + 0.2)).any() else None] for lo in (0, .2, .4, .6, .8)}
for a in ('cueonly_gated', 'ridegate', 'ridegate_cand2'):
    dj = collections.defaultdict(list)
    for r in pp: dj[r['dj']].append(ec(r, a) - ec(r, 'default'))
    pd = {k: (round(float(np.mean(v)), 1), len(v)) for k, v in dj.items()}
    out[a + '_per_dj_worst'] = sorted(pd.items(), key=lambda x: -x[1][0])[:5]; out[a + '_djs_worse'] = sum(v[0] > 0 for v in pd.values())
    w = sorted(pp, key=lambda r: -(ec(r, a) - ec(r, 'default')))[:6]
    out[a + '_worst_pairs'] = [dict(id=r['id'], d=round(ec(r, a) - ec(r, 'default'), 1), pro_out=round(r['pro_out']), pro_in=round(r['pro_in']), na=r['na'], ex=r[a]['exit'], cue=r[a]['cue'], dex=r['dex'], dcue=r['dcue']) for r in w]
out['folds_theta'] = {k: (v['v1']['theta'], v['v2']['theta'], v['v1']['tau'], v['C']['tau']) for k, v in d['folds'].items()}
json.dump(out, open(os.path.join(H, 'picker_1125_analysis.json'), 'w'), indent=1)
print(json.dumps({k: out[k] for k in ('means', 'hits', 'deltas', 'strata')}, indent=0))
for k in out:
    if k not in ('means', 'hits', 'deltas', 'strata'): print(k, out[k])
