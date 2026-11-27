"""n1127 analysis of nightly_1127_work/picker_1127_<cv|fresh>.json. Reference = ridegate (current engine default); also vs majority and
vs the old default. Grouped bootstrap by mix (4000, seed 20261127); fresh (one mix) resamples pairs (indicative only). Blend-length proxy
as n1126 (X=8 -> 5, 16 -> 10, 32 -> 18 bars). 'same as ridegate' = abstain relative to the current default. Breakdown-exit share =
exit (blend start) inside an outgoing breakdown section (picker_1119.sec_at == 3). usage: analyze_1127.py cv|fresh"""
import json, numpy as np, collections, os, sys
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H); W = os.path.join(H, 'nightly_1127_work'); mode = sys.argv[1]
import picker_1119 as P
d = json.load(open(os.path.join(W, f'picker_1127_{mode}.json'))); pp = d['per_pair']
P.W = W; P.SPENT_FRESH = {m['mix_id'] for m in json.load(open(os.path.join(H, 'fresh_mixes.json')))['mixes']}
SA = {r['id']: r['sa'] for r in P.rows_all()}
ARMS = [k for k, v in pp[0].items() if isinstance(v, dict)]
REF = 'ridegate'
ex = lambda r, a: abs(r[a]['exit'] - r['pro_out']); cu = lambda r, a: abs(r[a]['cue'] - r['pro_in']); ec = lambda r, a: (ex(r, a) + cu(r, a)) / 2
OV = {8: 5.0, 16: 10.0, 32: 18.0}
bl = lambda r, a: abs(OV.get(r[a]['X'], 10.0) - (r['pro_ov'] if r['pro_ov'] is not None else 10.0))
grp = (lambda r, i: r['mix']) if mode != 'fresh' else (lambda r, i: i)
gs = sorted({grp(r, i) for i, r in enumerate(pp)}, key=str); idx = collections.defaultdict(list)
for i, r in enumerate(pp): idx[grp(r, i)].append(i)
rng = np.random.default_rng(20261127); NB = 4000
BS = [np.concatenate([idx[gs[m]] for m in rng.choice(len(gs), len(gs))]) for _ in range(NB)]
def boot(f, a, b):
    A = np.array([f(r, a) - f(r, b) for r in pp]); s = [A[ii].mean() for ii in BS]
    return [round(float(A.mean()), 2), round(float(np.percentile(s, 2.5)), 2), round(float(np.percentile(s, 97.5)), 2)]
bdx = lambda r, a: float(P.sec_at(SA[r['id']], r[a]['exit']) == 3)
out = dict(mode=mode, n=len(pp), n_groups=len(gs), means={}, hits={}, deltas={})
for a in ARMS:
    out['means'][a] = dict(exit_cue=round(float(np.mean([ec(r, a) for r in pp])), 2), exit=round(float(np.mean([ex(r, a) for r in pp])), 2),
                           cue=round(float(np.mean([cu(r, a) for r in pp])), 2), blendlen=round(float(np.mean([bl(r, a) for r in pp])), 2),
                           same_as_old_default=round(float(np.mean([r[a]['is_default'] for r in pp])), 3),
                           same_as_ridegate=round(float(np.mean([(r[a]['exit'], r[a]['cue'], r[a]['X']) == (r[REF]['exit'], r[REF]['cue'], r[REF]['X']) for r in pp])), 3),
                           midtrack_exit_share=round(float(np.mean([r[a]['exit'] < r['na'] - 40 for r in pp])), 3),
                           breakdown_exit_share=round(float(np.mean([bdx(r, a) for r in pp])), 3))
    out['hits'][a] = {f'{k}@{t}': round(float(np.mean([f(r, a) <= t for r in pp])), 3) for k, f in (('exit', ex), ('cue', cu)) for t in (4, 8, 16)}
out['pro_breakdown_exit_share'] = round(float(np.mean([P.sec_at(SA[r['id']], r['pro_out']) == 3 for r in pp])), 3)
for a in ARMS:
    for ref in (REF, 'majority', 'default'):
        if a == ref: continue
        D = {m: boot(f, a, ref) for m, f in (('exit_cue', ec), ('exit', ex), ('cue', cu), ('blendlen', bl))}
        for t in (4, 8, 16):
            for nm, f in (('exit', ex), ('cue', cu)):
                m, lo, hi = boot(lambda r, x, f=f, t=t: -float(f(r, x) <= t), a, ref); D[f'{nm}_hit{t}_gain'] = [-m, -hi, -lo]
        out['deltas'][f'{a}_vs_{ref}'] = D
S = dict(pro_mid=[r for r in pp if r['pro_out'] < r['na'] - 40], pro_late=[r for r in pp if r['na'] - 40 <= r['pro_out'] < r['na'] - 12], pro_tail=[r for r in pp if r['pro_out'] >= r['na'] - 12])
out['strata'] = {nm: dict(n=len(L), exit_err={a: round(float(np.mean([ex(r, a) for r in L])), 1) for a in ARMS} if L else {}) for nm, L in S.items()}
try:
    from sklearn.metrics import roc_auc_score
    y = np.array([r['pro_out'] < r['na'] - 40 for r in pp])
    if 0 < y.sum() < len(y):
        for k in ('p_leave', 'p_leave_ctx', 'p_leave_tf'): out['ride_auc_' + k] = round(float(roc_auc_score(y, [r[REF][k] for r in pp])), 3)
except Exception as e: out['ride_auc_err'] = str(e)
for a in [x for x in ARMS if x.startswith('rg_')]:
    dj = collections.defaultdict(list)
    for r in pp: dj[r.get('dj', '?')].append(ec(r, a) - ec(r, REF))
    pd = {k: (round(float(np.mean(v)), 1), len(v)) for k, v in dj.items()}
    out[a + '_per_dj_worst'] = sorted(pd.items(), key=lambda x: -x[1][0])[:5]; out[a + '_djs_worse'] = sum(v[0] > 0 for v in pd.values()); out[a + '_n_djs'] = len(pd)
    w = sorted(pp, key=lambda r: -(ec(r, a) - ec(r, REF)))[:6]
    out[a + '_worst_pairs'] = [dict(id=r['id'], d=round(ec(r, a) - ec(r, REF), 1), pro_out=round(r['pro_out']), pro_in=round(r['pro_in']), na=r['na'], ex=r[a]['exit'], cue=r[a]['cue'], rg_ex=r[REF]['exit'], rg_cue=r[REF]['cue']) for r in w]
    out[a + '_better_worse_same_vs_ridegate'] = [int(sum(ec(r, a) < ec(r, REF) for r in pp)), int(sum(ec(r, a) > ec(r, REF) for r in pp)), int(sum(ec(r, a) == ec(r, REF) for r in pp))]
json.dump(out, open(os.path.join(W, f'analysis_1127_{mode}.json'), 'w'), indent=1)
for k in ('means', 'hits'): print(k); [print(' ', a, v) for a, v in out[k].items()]
print('deltas'); [print(' ', a, {m: v for m, v in D.items() if m in ('exit_cue', 'exit', 'cue', 'blendlen', 'exit_hit16_gain', 'exit_hit4_gain')}) for a, D in out['deltas'].items()]
for k in out:
    if k not in ('means', 'hits', 'deltas'): print(k, out[k])
