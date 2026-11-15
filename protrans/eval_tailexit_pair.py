#!/usr/bin/env python3
"""Like-for-like pair eval for TAIL_EXIT: same pinned window, default (rules.json) vs TAIL_EXIT=N.
Scores each against the pro clip, runs blend_diag (dip, spectral) and the must-pass set (eval_graphcut).
Does not write rules.json. Usage: python3 protrans/eval_tailexit_pair.py <pair_id> <out_dir> N [N ...]"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths, recreate
import run_admitted_tune as T
import eval_graphcut as EG


def main(pid, out_dir, Ns):
    os.makedirs(out_dir, exist_ok=True)
    rec = {r['id']: r for r in T.load_recs()}[pid]
    sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a'); sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
    rules = json.load(open(paths.RULES))
    assert 'TAIL_EXIT' not in rules
    d0 = recreate.recreate(rec['a']['yt'], rec['b']['yt'], sa, sb, hint_a_played_sec=rec['window']['hint_a_played_sec'],
                           rules=rules, tag='tep0')
    win, env = d0['win'], d0['env']
    res = dict(pick=pid, pair=rec['pair'], split=rec['split'], win=win, fam=d0['fam'], env=env, variants={})
    for N in [0] + list(Ns):
        e = dict(env)
        if N:
            e['TAIL_EXIT'] = str(N)
        tag = f'te_{pid}_n{N}'
        info = EG.render_pinned(rec, sa, sb, win, e, tag, out_dir)
        sc = EG.score_pair(rec, sa, sb, info['ours'])
        dg = EG.diag(rec, sa, sb, info, f'diag_{tag}', out_dir)
        M = json.load(open(info['meta_path']))
        tests = EG.run_must_pass(M, info['raw'] or info['master'], tag)
        snip = (info.get('pick') or {}).get('snip') or {}
        res['variants'][str(N)] = dict(score=sc['score'], score_v2=sc.get('score_v2'), breakdown=sc['breakdown'],
                                       dip=dg.get('sum_lows_dip_db'), spectral=dg.get('spectral'),
                                       tests={k: (v.get('pass_') if isinstance(v, dict) else v) for k, v in tests.items()},
                                       tail_exit=M['trans'][0].get('tail_exit'), bass_swap=M['trans'][0].get('bass_swap'),
                                       start_bar=M['trans'][0]['start_bar'], end_bar=M['trans'][0]['end_bar'],
                                       snip=snip, ours=info['ours'], raw=info['raw'], meta=info['meta_path'])
        print('PAIR', pid, 'N', N, sc['score'], dg.get('sum_lows_dip_db'), (dg.get('spectral') or {}).get('banger_clash_rate'),
              tests.get('all_pass'), M['trans'][0].get('tail_exit'), flush=True)
    json.dump(res, open(os.path.join(out_dir, f'pair_{pid}.json'), 'w'), indent=1, default=str)
    return res


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], [float(x) for x in sys.argv[3:]])
