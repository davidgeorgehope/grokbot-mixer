#!/usr/bin/env python3
"""33-pair eval of RANKER=1 against the current floor. Does not write rules.json.

Floor (BLEND_LOCK on): held-out 34.07, train 32.40, 0 fails.
Usage: python3 protrans/eval_ranker_v0.py
"""
from __future__ import annotations
import copy, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths, eval_cohort, run_admitted_tune as T

FLOOR = dict(held_out=34.07, train=32.40, n_fail=0)
VARIANT = 'ranker_v0'
WORKERS = int(os.environ.get('EVAL_WORKERS', '2'))


def main():
    os.environ.setdefault('OMP_NUM_THREADS', '1')
    rules = json.load(open(paths.RULES))
    assert int(rules.get('BLEND_LOCK') or 0) == 1
    trial = copy.deepcopy(rules)
    trial['RANKER'] = 1
    # do not persist; only this process / child workers see the flag via apply_rules
    recs = T.load_recs()
    rows = T.run_set_checkpointed(recs, trial, VARIANT, VARIANT[:6], workers=WORKERS)
    sm = T.summarize(rows)
    v2 = eval_cohort.summary_v2(rows)
    picks = []
    for r in rows:
        info = r.get('info') or r.get('pick') or {}
        # run_admitted_tune row shape: score, pick, id, split
        pick = r.get('pick') or {}
        picks.append(dict(id=r['id'], split=r.get('split'),
                          score=(r.get('score') or {}).get('score') if isinstance(r.get('score'), dict) else None,
                          fam=pick.get('fam'), win=pick.get('win'),
                          env=pick.get('env'), ranker=pick.get('ranker') or (r.get('info') or {}).get('ranker')))
    held = sm['test_mean']
    train = sm['train_mean']
    n_fail = sm['n_fail']
    clears = (held is not None and held + 1e-9 >= FLOOR['held_out']
              and train is not None and train + 1e-9 >= FLOOR['train']
              and n_fail <= FLOOR['n_fail'])
    out = dict(
        variant=VARIANT,
        v3=dict(train=train, test=held, n=sm['n'], n_fail=n_fail),
        v2=dict(train=v2['train_mean'], test=v2['test_mean']),
        by_dj=sm['by_dj'],
        floor=FLOOR,
        floors_held=clears,
        defaults_changed=False,
        flag='RANKER',
        flag_default=0,
        pairs=picks,
    )
    dest = os.path.join(paths.RESULTS, f'eval_{VARIANT}.json')
    json.dump(out, open(dest, 'w'), indent=2, default=str)
    print('RESULT ' + json.dumps({k: out[k] for k in out if k != 'pairs'}), flush=True)
    # Compare each pair's ranker pick to the BLEND_LOCK baseline checkpoint if present
    base_path = os.path.join(paths.RESULTS, 'eval_rca1117_blendlock3.json')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
