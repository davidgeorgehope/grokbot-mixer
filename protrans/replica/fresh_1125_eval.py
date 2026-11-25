"""2026-11-25: score the unspent unseen-DJ fresh mixes (zaklynskyi_SKL2rC3tcug + eidan_J5bKdjl2xKo)
ONCE for epg_stack vs base (default) for 0 new hard fails (both official hardcheck.check AND
final_eval.flags HC_A / HC_B v2). Marks mixes spent in fresh_mixes.json after scoring once.
Does not write rules.json or defaults.
"""
import json, os, pickle, sys, time
import numpy as np

H = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, H)
import final_eval as FE

MIX_IDS = ['zaklynskyi_SKL2rC3tcug', 'eidan_J5bKdjl2xKo']
V = dict(base='fdef1125', epg_stack='fepgk1125')
SEED = 20261125
N_BOOT = 4000


def rows(v):
    out = {}
    p = os.path.join(H, 'gate_ckpt', v + '.jsonl')
    if not os.path.exists(p):
        return out
    for l in open(p):
        r = json.loads(l)
        if not r.get('error') and r.get('mix') in MIX_IDS:
            out[r['id']] = r
    return out


def arrs(v):
    p = os.path.join(H, 'hc2_cache', f'arr_{v}.pkl')
    return pickle.load(open(p, 'rb')) if os.path.exists(p) else {}


def _hard(r):
    return r.get('hard') or r.get('hardcheck') or {}


def exit_cue(r):
    e = r.get('err') or {}
    ex, cu = e.get('exit'), e.get('cue')
    if ex is None or cu is None:
        return None
    return (float(ex) + float(cu)) / 2.0


def bootstrap_pair(ids, R_arm, R_base):
    ds = [exit_cue(R_arm[i]) - exit_cue(R_base[i]) for i in ids
          if exit_cue(R_arm[i]) is not None and exit_cue(R_base[i]) is not None]
    if not ds:
        return None
    ds = np.array(ds, float)
    rng = np.random.default_rng(SEED)
    bs = [ds[rng.integers(0, len(ds), len(ds))].mean() for _ in range(N_BOOT)]
    lo, hi = np.percentile(bs, [2.5, 97.5])
    return dict(n=len(ds), mean_delta=round(float(ds.mean()), 3),
                ci=[round(float(lo), 3), round(float(hi), 3)],
                includes_zero=bool(lo <= 0 <= hi))


def summarize(ids, R, F):
    out = dict(n=len(ids), ids=ids, arms={})
    for k in V:
        hc1 = {i: bool(_hard(R[k][i]).get('hard_fail')) for i in ids}
        hc2 = {i: bool(F[k][i]['HC_A'] or F[k][i]['HC_B']) for i in ids}
        new_hc1 = [i for i in ids if hc1[i] and not _hard(R['base'][i]).get('hard_fail')]
        new_hc2 = [i for i in ids if hc2[i] and not (F['base'][i]['HC_A'] or F['base'][i]['HC_B'])]
        changed = [i for i in ids if R[k][i].get('win') != R['base'][i].get('win')]

        def m(f):
            xs = [R[k][i]['err'][f] for i in ids if (R[k][i].get('err') or {}).get(f) is not None]
            return round(float(np.mean(xs)), 2) if xs else None

        fe = [R[k][i].get('fade_err') for i in ids if isinstance(R[k][i].get('fade_err'), (int, float))]
        ec = [exit_cue(R[k][i]) for i in ids if exit_cue(R[k][i]) is not None]
        arm = dict(
            hardcheck_v1_fails=sum(hc1.values()),
            hardcheck_v1_fail_ids=[i for i in ids if hc1[i]],
            new_hardcheck_v1_fails=new_hc1,
            hardcheck_v1_counts={
                'beat_clash': sum(bool(_hard(R[k][i]).get('beat_clash')) for i in ids),
                'bass_hole': sum(bool(_hard(R[k][i]).get('bass_hole')) for i in ids),
                'pumping': sum(bool(_hard(R[k][i]).get('pumping')) for i in ids),
            },
            hc2_fails=sum(hc2.values()),
            hc2_fail_ids=[i for i in ids if hc2[i]],
            new_hc2_fails=new_hc2,
            hc2_counts={c: sum(F[k][i][c] for i in ids) for c in ('hole_v2', 'clash_v1', 'clash_v2', 'halfbeat', 'pump')},
            zero_new_hard_fails=(not new_hc1 and not new_hc2),
            changed=changed,
            n_changed=len(changed),
            exit_err=m('exit'),
            cue_err=m('cue'),
            exit_cue_mean=round(float(np.mean(ec)), 2) if ec else None,
            overlap_err=m('overlap'),
            swap_err=m('swap'),
            fade_err=round(float(np.mean(fe)), 3) if fe else None,
        )
        if k != 'base':
            arm['delta_exit_cue_pair'] = bootstrap_pair(ids, R[k], R['base'])
        out['arms'][k] = arm
    out['pass_zero_new_hard_fails'] = out['arms']['epg_stack']['zero_new_hard_fails']
    return out


R = {k: rows(v) for k, v in V.items()}
A = {k: arrs(v) for k, v in V.items()}
ids = sorted(set.intersection(*[set(R[k]) & set(A[k]) for k in V]))
if not ids:
    raise SystemExit(f'No scored rows found for {MIX_IDS}')
F = {k: {i: FE.flags(A[k][i]) for i in ids} for k in V}

res = dict(
    mix_ids=MIX_IDS,
    combined=summarize(ids, R, F),
    by_mix={},
)
for mid in MIX_IDS:
    m_ids = [i for i in ids if i.startswith(mid + '__')]
    if m_ids:
        res['by_mix'][mid] = summarize(m_ids, R, F)

for label, sub in [('COMBINED', res['combined'])] + [(m, res['by_mix'][m]) for m in res['by_mix']]:
    print('===', label, 'n=', sub['n'], 'pass=', sub['pass_zero_new_hard_fails'], flush=True)
    for k in V:
        print(' ', k, json.dumps(sub['arms'][k]), flush=True)

out_path = os.path.join(H, 'fresh_1125_eval.json')
json.dump(res, open(out_path, 'w'), indent=1)
print('WROTE', out_path, flush=True)

fm = json.load(open(os.path.join(H, 'fresh_mixes.json')))
stamp = time.strftime('%Y-%m-%d %H:%M ET')
for x in fm['mixes']:
    if x['mix_id'] in res['by_mix'] and not x.get('spent'):
        n_m = res['by_mix'][x['mix_id']]['n']
        x['spent'] = True
        x['spent_on'] = f'{stamp} (fresh_1125 epg_stack vs base, once, n={n_m})'
        print('MARKED SPENT', x['mix_id'], 'n', n_m, flush=True)
json.dump(fm, open(os.path.join(H, 'fresh_mixes.json'), 'w'), indent=1)
