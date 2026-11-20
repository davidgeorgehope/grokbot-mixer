"""2026-11-20 nightly: score the Sirenity fresh mix ONCE for the frozen epg candidates (promotion_criteria_1120.json):
zero new hard fails (official HC_A / HC_B v2, final_eval.flags) vs the rendered default on the same pairs; plus decision-level
errors vs the pro (exit, cue, overlap, bass-swap, fade shape) from eval_gate rows. Marks the mix spent in fresh_mixes.json."""
import json, os, sys, numpy as np, time
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import final_eval as FE, pickle
V = dict(default='fdef1120', epg_strict='fepgs1120', epg_drop='fepgd1120', epg_stack='fepgk1120')
def rows(v):
    out = {}
    for l in open(os.path.join(H, 'gate_ckpt', v + '.jsonl')):
        r = json.loads(l)
        if not r.get('error'): out[r['id']] = r
    return out
R = {k: rows(v) for k, v in V.items()}
A = {k: (pickle.load(open(os.path.join(H, 'hc2_cache', f'arr_{v}.pkl'), 'rb')) if os.path.exists(os.path.join(H, 'hc2_cache', f'arr_{v}.pkl')) else {}) for k, v in V.items()}
ids = sorted(set.intersection(*[set(R[k]) & set(A[k]) for k in V]))
F = {k: {i: FE.flags(A[k][i]) for i in ids} for k in V}
res = dict(mix='sirenity_ofcHup56lME', n=len(ids), ids=ids, arms={})
for k in V:
    hf = {i: bool(F[k][i]['HC_A'] or F[k][i]['HC_B']) for i in ids}
    new = [i for i in ids if hf[i] and not (F['default'][i]['HC_A'] or F['default'][i]['HC_B'])]
    fixed = [i for i in ids if not hf[i] and (F['default'][i]['HC_A'] or F['default'][i]['HC_B'])]
    changed = [i for i in ids if R[k][i]['win'] != R['default'][i]['win']]
    m = lambda f: round(float(np.mean([R[k][i]['err'][f] for i in ids if R[k][i]['err'].get(f) is not None])), 2) if ids else None
    fe = [R[k][i].get('fade_err') for i in ids if isinstance(R[k][i].get('fade_err'), (int, float))]
    res['arms'][k] = dict(hard_fail=sum(hf.values()), new_fails=new, fixed=fixed, changed=changed, exit_err=m('exit'), cue_err=m('cue'), overlap_err=m('overlap'), swap_err=m('swap'),
                          fade_err=round(float(np.mean(fe)), 3) if fe else None,
                          checks={c: sum(F[k][i][c] for i in ids) for c in ('hole_v2', 'clash_v1', 'clash_v2', 'halfbeat', 'pump')},
                          zero_new_hard_fails=not new)
    print(k, json.dumps(res['arms'][k]), flush=True)
json.dump(res, open(os.path.join(H, 'fresh1120_eval.json'), 'w'), indent=1)
fm = json.load(open(os.path.join(H, 'fresh_mixes.json')))
for x in fm['mixes']:
    if x['mix_id'] == res['mix']: x['spent'] = True; x['spent_on'] = time.strftime('%Y-%m-%d %H:%M ET') + ' (n1120 epg candidates, once)'
json.dump(fm, open(os.path.join(H, 'fresh_mixes.json'), 'w'), indent=1)
