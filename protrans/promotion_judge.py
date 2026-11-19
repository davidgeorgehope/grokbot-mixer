#!/usr/bin/env python3
"""Night-win judges for promotion candidates.

epg_drop (and the stacked arm) use a deliberate change of judge made on the listener's
direct listening, not a loosened threshold: pro-match may sit within the
mix-grouped bootstrap CI of the floor (the CI of arm minus floor must include 0).
epg_strict still uses "held-out and train mean not worse than the floor."
This module does not write rules.json.
"""
from __future__ import annotations
import numpy as np

SEED = 20261119
N_BOOT = 4000


def _mix_of(row):
    return row.get('mix') or (row['id'].rsplit('__', 1)[0] if row.get('id') else None)


def _score(row):
    s = row['score']
    return s['score'] if isinstance(s, dict) else float(s)


def paired_delta_ci(base_rows, arm_rows, split, seed=SEED, n_boot=N_BOOT):
    """Mix-grouped bootstrap CI (4000, seed 20261119) of arm minus floor on one split."""
    B = {r['id']: r for r in base_rows if r.get('split') == split and r.get('score') and not r.get('error')}
    A = {r['id']: r for r in arm_rows if r.get('split') == split and r.get('score') and not r.get('error')}
    ids = sorted(set(B) & set(A))
    if not ids:
        return None
    rows = [dict(id=i, mix=_mix_of(B[i]), d=_score(A[i]) - _score(B[i])) for i in ids]
    by = {}
    for r in rows:
        by.setdefault(r['mix'], []).append(r['d'])
    rng = np.random.default_rng(seed)
    G = [np.array(v, float) for v in by.values()]
    bs = [np.concatenate([G[j] for j in rng.integers(0, len(G), len(G))]).mean() for _ in range(n_boot)]
    lo, hi = np.percentile(bs, [2.5, 97.5])
    return dict(n=len(rows), n_mix=len(by),
                mean_delta=round(float(np.mean([r['d'] for r in rows])), 3),
                ci=[round(float(lo), 3), round(float(hi), 3)],
                includes_zero=bool(lo <= 0 <= hi))


def means_not_worse(base_sm, arm_sm):
    return (arm_sm.get('test_mean') is not None and base_sm.get('test_mean') is not None
            and arm_sm.get('train_mean') is not None and base_sm.get('train_mean') is not None
            and arm_sm['test_mean'] + 1e-9 >= base_sm['test_mean']
            and arm_sm['train_mean'] + 1e-9 >= base_sm['train_mean'])


def promotion_night_win(meta, base_sm, arm_sm, base_rows=None, arm_rows=None):
    """Return (ok, why). Official hard-fail (HC v2, leave-one-DJ-out, per DJ) and
    the Sirenity fresh-mix "zero new hard fails" check live in promotion_criteria_1120.json
    and are not fully computed inside the nightly scorer loop."""
    judge = (meta or {}).get('judge') or 'not_worse_than_floor_mean'
    fail_ok = arm_sm.get('n_fail', 0) <= base_sm.get('n_fail', 0)
    if judge == 'pro_match_within_floor_ci':
        tes = paired_delta_ci(base_rows or [], arm_rows or [], 'test')
        trn = paired_delta_ci(base_rows or [], arm_rows or [], 'train')
        ci_ok = bool(tes and trn and tes.get('includes_zero') and trn.get('includes_zero'))
        ok = bool(ci_ok and fail_ok)
        why = (f"listening judge: held-out delta {tes} train {trn}; render-fails "
               f"{base_sm.get('n_fail')} -> {arm_sm.get('n_fail')}"
               + ('' if ok else ' (not a night-win)'))
        return ok, why
    ok = bool(means_not_worse(base_sm, arm_sm) and fail_ok)
    why = (f"held-out {base_sm.get('test_mean')} -> {arm_sm.get('test_mean')}, "
           f"train {base_sm.get('train_mean')} -> {arm_sm.get('train_mean')}")
    if ok:
        why = 'promotion night-win: ' + why
    else:
        why = 'promotion night lost (' + why + ')'
    return ok, why
