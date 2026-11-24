"""2026-11-23: score the YoloWich fresh mix ONCE for the frozen epg candidates.

Zero new official hard fails (HC_A / HC_B v2, final_eval.flags) vs the rendered
default on the same pairs; decision-level errors vs the pro; mix-grouped and
pair-resampled bootstrap 95% CIs of (arm minus default) exit+cue bar error.
Marks the mix spent in fresh_mixes.json after this single pass.
Does not write rules.json. Does not reopen the locked Liquicity/Hospital holdout
(promotion_criteria_1120.json: already opened 2026-11-19, not required for these
flag candidates; a further look would be a repeated opening).
"""
import json, os, sys, time
import numpy as np

H = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, H)
import final_eval as FE
import pickle

V = dict(default='fdef1123', epg_strict='fepgs1123', epg_drop='fepgd1123', epg_stack='fepgk1123')
MIX = 'yolowich_FIdBhH3SuXk'
SEED = 20261119
N_BOOT = 4000


def rows(v):
    out = {}
    p = os.path.join(H, 'gate_ckpt', v + '.jsonl')
    if not os.path.exists(p):
        return out
    for l in open(p):
        r = json.loads(l)
        if not r.get('error'):
            out[r['id']] = r
    return out


def arrs(v):
    p = os.path.join(H, 'hc2_cache', f'arr_{v}.pkl')
    return pickle.load(open(p, 'rb')) if os.path.exists(p) else {}


def exit_cue(r):
    e = r.get('err') or {}
    ex, cu = e.get('exit'), e.get('cue')
    if ex is None or cu is None:
        return None
    return float(ex) + float(cu)


def bootstrap_delta(ids, R_arm, R_base, group='mix', seed=SEED, n_boot=N_BOOT):
    """Bootstrap CI of mean (arm - default) exit+cue error. group='mix' or 'pair'."""
    rows = []
    for i in ids:
        a, b = exit_cue(R_arm[i]), exit_cue(R_base[i])
        if a is None or b is None:
            continue
        mix = i.rsplit('__', 1)[0]
        rows.append(dict(id=i, mix=mix, d=a - b))
    if not rows:
        return None
    if group == 'pair':
        groups = [np.array([r['d']], float) for r in rows]
    else:
        by = {}
        for r in rows:
            by.setdefault(r['mix'], []).append(r['d'])
        groups = [np.array(v, float) for v in by.values()]
    rng = np.random.default_rng(seed)
    bs = [np.concatenate([groups[j] for j in rng.integers(0, len(groups), len(groups))]).mean()
          for _ in range(n_boot)]
    lo, hi = np.percentile(bs, [2.5, 97.5])
    mean = float(np.mean([r['d'] for r in rows]))
    return dict(n=len(rows), n_groups=len(groups), group=group,
                mean_delta=round(mean, 3),
                ci=[round(float(lo), 3), round(float(hi), 3)],
                includes_zero=bool(lo <= 0 <= hi),
                note=('mix-grouped CI is degenerate with a single mix (every draw is the observed mean)'
                      if group == 'mix' and len(groups) == 1 else None))


R = {k: rows(v) for k, v in V.items()}
A = {k: arrs(v) for k, v in V.items()}
ids = sorted(set.intersection(*[set(R[k]) & set(A[k]) for k in V]))
F = {k: {i: FE.flags(A[k][i]) for i in ids} for k in V}
res = dict(
    mix=MIX,
    url='https://www.youtube.com/watch?v=FIdBhH3SuXk',
    title='Hybrid Minds - Drum n Bass Listening Liquid Set',
    dj='YoloWich',
    n=len(ids),
    ids=ids,
    locked_holdout='not reopened (promotion_criteria_1120.json: already opened 2026-11-19; not required for these flag candidates)',
    arms={},
)

for k in V:
    hf = {i: bool(F[k][i]['HC_A'] or F[k][i]['HC_B']) for i in ids}
    new = [i for i in ids if hf[i] and not (F['default'][i]['HC_A'] or F['default'][i]['HC_B'])]
    fixed = [i for i in ids if not hf[i] and (F['default'][i]['HC_A'] or F['default'][i]['HC_B'])]
    changed = [i for i in ids if R[k][i].get('win') != R['default'][i].get('win')]
    def m(f):
        xs = [R[k][i]['err'][f] for i in ids if (R[k][i].get('err') or {}).get(f) is not None]
        return round(float(np.mean(xs)), 2) if xs else None
    fe = [R[k][i].get('fade_err') for i in ids if isinstance(R[k][i].get('fade_err'), (int, float))]
    ec = [exit_cue(R[k][i]) for i in ids if exit_cue(R[k][i]) is not None]
    arm = dict(
        hard_fail=sum(hf.values()),
        new_fails=new,
        fixed=fixed,
        changed=changed,
        exit_err=m('exit'),
        cue_err=m('cue'),
        overlap_err=m('overlap'),
        swap_err=m('swap'),
        fade_err=round(float(np.mean(fe)), 3) if fe else None,
        exit_cue_mean=round(float(np.mean(ec)), 2) if ec else None,
        checks={c: sum(F[k][i][c] for i in ids) for c in ('hole_v2', 'clash_v1', 'clash_v2', 'halfbeat', 'pump')},
        zero_new_hard_fails=not new,
    )
    if k != 'default':
        arm['delta_exit_cue_mix_grouped'] = bootstrap_delta(ids, R[k], R['default'], 'mix')
        arm['delta_exit_cue_pair'] = bootstrap_delta(ids, R[k], R['default'], 'pair')
    res['arms'][k] = arm
    print(k, json.dumps(arm), flush=True)

res['pass'] = {k: res['arms'][k]['zero_new_hard_fails'] for k in V if k != 'default'}
json.dump(res, open(os.path.join(H, 'fresh1123_eval.json'), 'w'), indent=1)

fm = json.load(open(os.path.join(H, 'fresh_mixes.json')))
for x in fm['mixes']:
    if x['mix_id'] == MIX:
        x['spent'] = True
        x['spent_on'] = time.strftime('%Y-%m-%d %H:%M ET') + f' (n1123 epg candidates, once, n={len(ids)})'
json.dump(fm, open(os.path.join(H, 'fresh_mixes.json'), 'w'), indent=1)
print('SPENT', MIX, 'n', len(ids), 'pass', res['pass'], flush=True)
