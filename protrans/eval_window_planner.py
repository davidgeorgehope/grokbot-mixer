#!/usr/bin/env python3
"""Type accuracy of the mid-track window planner, and an optional like-for-like
cohort (eval_cohort) with rules['window_planner']=1. Does not edit rules.json.

Usage:
  python3 protrans/eval_window_planner.py           # type accuracy only
  python3 protrans/eval_window_planner.py --cohort  # also run the 33-pair eval
"""
from __future__ import annotations
import argparse, json, os, sys, copy, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'src2'))
import paths
import admit
import run_admitted_tune as T
import window_planner as WP
import sections
import bassgap
from recreate import incoming_hole_bars

FEAT = os.path.join(paths.RESULTS, 'snapin_features_2026-11-15.json')
BASE = 'd1115_xp_045'
VARIANT = 'wp1115'


def _lows(yt):
    p = os.path.join(paths.SRC2, 'st', f'{yt}.json')
    return np.array(json.load(open(p))['bar']['low'], float)


def type_table():
    rows = {}
    for line in open(os.path.join(paths.RESULTS, 'score_ckpt', BASE + '.jsonl')):
        r = json.loads(line)
        if r.get('id') and r.get('pick'):
            rows[r['id']] = r
    shapes = {}
    if os.path.exists(FEAT):
        for r in json.load(open(FEAT)).get('pairs') or []:
            shapes[r['id']] = r
    recs = {r['id']: r for r in admit.load_admitted()}
    out = []
    cwd = os.getcwd(); os.chdir(paths.SRC2)
    try:
        for rid, r in sorted(rows.items()):
            rec = recs[rid]
            a, b = rec['a']['yt'], rec['b']['yt']
            sa, sb = sections.get(a), sections.get(b)
            lo_a, lo_b = _lows(a), _lows(b)
            default = r['pick']['win']
            ch = WP.select(default, sa, sb, lo_a, lo_b)
            sh = (shapes.get(rid) or {}).get('shape')
            gold = WP.classify_pro_shape(sh, pair_id=rid)
            out.append(dict(
                id=rid, split=r.get('split'), score=(r.get('score') or {}).get('score') if isinstance(r.get('score'), dict) else r.get('score'),
                default=default, default_holes=ch.get('default_holes'), outro_holes=ch.get('outro_holes'),
                intro=int(sb.get('intro_end') or 0),
                pro_shape=sh, gold=gold, pred=ch['type'], win=ch['win'],
                fade=ch.get('fade_env') or {}, reason=ch.get('reason'),
                exact=ch['type'] == gold,
                mid_ok=(ch['type'] in ('breakdown_drop', 'drop1_end', 'drop_drop')) == (gold in ('breakdown_drop', 'drop1_end', 'drop_drop')),
            ))
    finally:
        os.chdir(cwd)
    return out


def summarize(rows):
    def pack(rr):
        n = len(rr)
        return dict(n=n,
                    exact=sum(1 for r in rr if r['exact']),
                    exact_rate=None if not n else round(sum(1 for r in rr if r['exact']) / n, 3),
                    mid_ok=sum(1 for r in rr if r['mid_ok']),
                    mid_ok_rate=None if not n else round(sum(1 for r in rr if r['mid_ok']) / n, 3),
                    switched=sum(1 for r in rr if r['pred'] != 'outro_intro'),
                    false_mid=sum(1 for r in rr if r['gold'] == 'outro_intro' and r['pred'] != 'outro_intro'),
                    missed_mid=sum(1 for r in rr if r['gold'] in ('breakdown_drop', 'drop1_end', 'drop_drop') and r['pred'] == 'outro_intro'))
    return dict(all=pack(rows),
                train=pack([r for r in rows if r['split'] == 'train']),
                test=pack([r for r in rows if r['split'] == 'test']))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--cohort', action='store_true')
    args = ap.parse_args()
    rows = type_table()
    summ = summarize(rows)
    targets = {r['id']: dict(pred=r['pred'], win=r['win'], fade=r['fade'], reason=r['reason'])
               for r in rows if r['id'] in ('hybrid_minds_ukf__19', 'hybrid_minds_ukf__25')}
    out = dict(gap_db=float(bassgap.GAP_DB), hole_min_16=WP.hole_min(16), short_intro=WP.SHORT_INTRO,
               baseline=BASE, held_out_floor=34.05, summary=summ, targets=targets, rows=rows)
    dest = os.path.join(paths.RESULTS, 'eval_window_planner_types_2026-11-15.json')
    json.dump(out, open(dest, 'w'), indent=2, default=str)
    print('TYPES', json.dumps(summ), flush=True)
    print('TARGETS', json.dumps(targets), flush=True)
    print('WROTE', dest, flush=True)
    if not args.cohort:
        return out
    rules = json.load(open(paths.RULES))
    trial = copy.deepcopy(rules)
    trial['window_planner'] = 1
    recs = T.load_recs()
    scored = T.run_set_checkpointed(recs, trial, VARIANT, 'wp')
    sm = T.summarize(scored)
    keep = (sm['test_mean'] is not None and sm['test_mean'] + 1e-9 >= 34.05 and sm['n_fail'] == 0)
    cohort = dict(variant=VARIANT, summary=sm, keep=keep,
                  floor=dict(train=32.26, test=34.05, n=33, n_fail=0))
    cdest = os.path.join(paths.RESULTS, f'eval_{VARIANT}.json')
    json.dump(cohort, open(cdest, 'w'), indent=2, default=str)
    print('COHORT', json.dumps(cohort, default=str), flush=True)
    print('WROTE', cdest, flush=True)
    return out


if __name__ == '__main__':
    main()
