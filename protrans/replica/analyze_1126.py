"""n1126 analysis of nightly_1126_work/picker_1126_<cv|fresh|holdout>.json: grouped bootstrap by mix (4000, seed 20261126) vs default
and vs majority; hit rates; strata (pro rode to the outro vs left mid-track vs tail entry); worst pairs / DJs; ride-gate AUC.
Blend-length proxy (audible overlap): X=8 -> 5, 16 -> 10, 32 -> 18 bars (11-19 map plus the 8-bar tail blend).
For fresh (one mix) the bootstrap is by PAIR (indicative only). usage: analyze_1126.py cv|fresh|holdout [stem, default picker_1126]"""
import json, numpy as np, collections, os, sys
H = os.path.dirname(os.path.abspath(__file__)); W = os.path.join(H, 'nightly_1126_work'); mode = sys.argv[1]; stem = sys.argv[2] if len(sys.argv) > 2 else 'picker_1126'
d = json.load(open(os.path.join(W, f'{stem}_{mode}.json'))); pp = d['per_pair']
ARMS = [k for k, v in pp[0].items() if isinstance(v, dict) and k != 'default']
ex = lambda r, a: abs(r[a]['exit'] - r['pro_out']); cu = lambda r, a: abs(r[a]['cue'] - r['pro_in']); ec = lambda r, a: (ex(r, a) + cu(r, a)) / 2
OV = {8: 5.0, 16: 10.0, 32: 18.0}
bl = lambda r, a: abs(OV.get(r[a]['X'], 10.0) - (r['pro_ov'] if r['pro_ov'] is not None else 10.0))
grp = (lambda r, i: r['mix']) if mode != 'fresh' else (lambda r, i: i)
gs = sorted({grp(r, i) for i, r in enumerate(pp)}, key=str); idx = collections.defaultdict(list)
for i, r in enumerate(pp): idx[grp(r, i)].append(i)
rng = np.random.default_rng(20261126); NB = 4000
BS = [np.concatenate([idx[gs[m]] for m in rng.choice(len(gs), len(gs))]) for _ in range(NB)]
def boot(f, a, b):
    A = np.array([f(r, a) - f(r, b) for r in pp]); s = [A[ii].mean() for ii in BS]
    return [round(float(A.mean()), 2), round(float(np.percentile(s, 2.5)), 2), round(float(np.percentile(s, 97.5)), 2)]
out = dict(mode=mode, n=len(pp), n_groups=len(gs), means={}, hits={}, deltas={})
for a in ['default'] + ARMS:
    out['means'][a] = dict(exit_cue=round(float(np.mean([ec(r, a) for r in pp])), 2), exit=round(float(np.mean([ex(r, a) for r in pp])), 2),
                           cue=round(float(np.mean([cu(r, a) for r in pp])), 2), blendlen=round(float(np.mean([bl(r, a) for r in pp])), 2),
                           abstain=round(float(np.mean([r[a]['is_default'] for r in pp])), 3),
                           exit_moved=round(float(np.mean([r[a]['exit'] != r['default']['exit'] for r in pp])), 3),
                           cue_moved=round(float(np.mean([r[a]['cue'] != r['default']['cue'] for r in pp])), 3),
                           midtrack_exit_share=round(float(np.mean([r[a]['exit'] < r['na'] - 40 for r in pp])), 3),
                           tail8_share=round(float(np.mean([r[a]['X'] == 8 for r in pp])), 3))
    out['hits'][a] = {f'{k}@{t}': round(float(np.mean([f(r, a) <= t for r in pp])), 3) for k, f in (('exit', ex), ('cue', cu)) for t in (4, 8, 16)}
for a in ARMS:
    for ref in ('default', 'majority'):
        if a == ref: continue
        D = {m: boot(f, a, ref) for m, f in (('exit_cue', ec), ('exit', ex), ('cue', cu), ('blendlen', bl))}
        for t in (4, 8, 16):
            for nm, f in (('exit', ex), ('cue', cu)):
                m, lo, hi = boot(lambda r, x, f=f, t=t: -float(f(r, x) <= t), a, ref); D[f'{nm}_hit{t}_gain'] = [-m, -hi, -lo]
        out['deltas'][f'{a}_vs_{ref}'] = D
S = dict(pro_mid=[r for r in pp if r['pro_out'] < r['na'] - 40], pro_late=[r for r in pp if r['na'] - 40 <= r['pro_out'] < r['na'] - 12], pro_tail=[r for r in pp if r['pro_out'] >= r['na'] - 12])
out['strata'] = {nm: dict(n=len(L), exit_err={a: round(float(np.mean([ex(r, a) for r in L])), 1) for a in ['default'] + ARMS} if L else {}) for nm, L in S.items()}
try:
    from sklearn.metrics import roc_auc_score
    y = np.array([r['pro_out'] < r['na'] - 40 for r in pp])
    if 0 < y.sum() < len(y):
        out['ride_auc'] = round(float(roc_auc_score(y, [r['default']['p_leave'] for r in pp])), 3)
        if pp[0]['default'].get('p_leave_tf') is not None: out['ride_auc_tf'] = round(float(roc_auc_score(y, [r['default']['p_leave_tf'] for r in pp])), 3)
except Exception as e: out['ride_auc_err'] = str(e)
for a in [x for x in ('ridegate', 'ridegate_tail', 'cueonly_gated', 'ridegate_conf') if x in ARMS]:
    dj = collections.defaultdict(list)
    for r in pp: dj[r.get('dj', '?')].append(ec(r, a) - ec(r, 'default'))
    pd = {k: (round(float(np.mean(v)), 1), len(v)) for k, v in dj.items()}
    out[a + '_per_dj_worst'] = sorted(pd.items(), key=lambda x: -x[1][0])[:5]; out[a + '_djs_worse'] = sum(v[0] > 0 for v in pd.values()); out[a + '_n_djs'] = len(pd)
    w = sorted(pp, key=lambda r: -(ec(r, a) - ec(r, 'default')))[:6]
    out[a + '_worst_pairs'] = [dict(id=r['id'], d=round(ec(r, a) - ec(r, 'default'), 1), pro_out=round(r['pro_out']), pro_in=round(r['pro_in']), na=r['na'], ex=r[a]['exit'], cue=r[a]['cue'], X=r[a]['X'], dex=r['dex'], dcue=r['dcue']) for r in w]
    out[a + '_better_worse_same'] = [int(sum(ec(r, a) < ec(r, 'default') for r in pp)), int(sum(ec(r, a) > ec(r, 'default') for r in pp)), int(sum(ec(r, a) == ec(r, 'default') for r in pp))]
json.dump(out, open(os.path.join(W, f'analysis_{stem[7:]}_{mode}.json'), 'w'), indent=1)
for k in ('means', 'hits'): print(k); [print(' ', a, v) for a, v in out[k].items()]
print('deltas'); [print(' ', a, v) for a, v in out['deltas'].items()]
for k in out:
    if k not in ('means', 'hits', 'deltas'): print(k, out[k])
