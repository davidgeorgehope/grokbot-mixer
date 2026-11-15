#!/usr/bin/env python3
"""TAIL_EXIT (src2/tail_exit.py) like-for-like diagnostics on cohort runs already scored by eval_cohort.py.

For each pair in each variant's checkpoint (the renders left in /tmp/protrans_bench by recreate):
blend_diag summary (summed-lows dip, half-beat, Manabe spectral collision / continuity / banger clash) and the
must-pass set from eval_graphcut.run_must_pass (bass-gap, L1, N1, X1, bass-never-doubles, outgoing fader tail
with RIDE_FRAC 0.15, V1), plus the designed tail from the meta. Writes results/eval_tailexit_<variant>.json and
prints per-split medians. Changes no rules or thresholds.
Usage: python3 protrans/eval_tailexit.py <variant> [<variant> ...]
"""
import glob, json, os, sys, traceback
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths
import run_admitted_tune as T
import eval_graphcut as EG


def diag_row(rec, row):
    sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a'); sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
    base = os.path.splitext(row['ours'])[0]
    metas = glob.glob(base + '_*_meta.json')
    if not metas:
        return dict(error='no meta')
    M = json.load(open(metas[0]))
    out = dict(meta=metas[0])
    sys.path.insert(0, paths.SRC2)
    cwd = os.getcwd(); os.chdir(paths.SRC2)
    try:
        import blend_diag
        png = base + '_diag.png'
        summ = blend_diag.figure(M, 0, png, rec['id'], pro=rec['pro_clip'], src_a=sa, src_b=sb, ours=row['ours'])
        out['dip'] = summ.get('sum_lows_dip_db')
        out['spectral'] = summ.get('spectral')
        out['halfbeat'] = summ.get('halfbeat')
    except Exception as e:
        out['diag_error'] = f'{type(e).__name__}: {e}'[-300:]
    finally:
        os.chdir(cwd)
    try:
        tests = EG.run_must_pass(M, base + '_raw.wav', 'te')
        out['tests'] = {k: (v.get('pass_') if isinstance(v, dict) else v) for k, v in tests.items()}
        out['test_fail_detail'] = {k: v.get('failures') for k, v in tests.items() if isinstance(v, dict) and v.get('pass_') is False}
        out['all_pass'] = tests.get('all_pass')
    except Exception as e:
        out['tests_error'] = f'{type(e).__name__}: {e}'[-300:]
        traceback.print_exc()
    t = M['trans'][0]
    out['tail_exit'] = t.get('tail_exit')
    xs = np.array(t['xfader'], float); g = 20 * np.log10(np.cos(xs[:, 1] * np.pi / 2) + 1e-9)
    k = np.flatnonzero(g <= -24)
    if t.get('bass_swap'):
        out['designed_tail24'] = round(float(xs[k[0], 0] if len(k) else xs[-1, 0]) - float(t['bass_swap'][1]), 3)
    return out


def med(xs):
    xs = [x for x in xs if x is not None]
    return None if not xs else round(float(np.median(xs)), 4)


def main(variants):
    recs = {r['id']: r for r in T.load_recs()}
    allres = {}
    for var in variants:
        rows = T.load_ckpt(var)
        res = {}
        for rid, row in sorted(rows.items()):
            if rid not in recs or not row.get('ours') or not os.path.exists(row['ours']):
                continue
            r = diag_row(recs[rid], row)
            r['split'] = recs[rid]['split']; r['score'] = (row.get('score') or {}).get('score')
            res[rid] = r
            print(var, rid, r.get('all_pass'), r.get('dip'), (r.get('spectral') or {}).get('banger_clash_rate'),
                  r.get('designed_tail24'), flush=True)
        summ = {}
        for split in ('train', 'test', 'all'):
            rr = [v for v in res.values() if split == 'all' or v['split'] == split]
            sp = lambda k: med([(v.get('spectral') or {}).get(k) for v in rr])
            summ[split] = dict(n=len(rr), all_pass=sum(1 for v in rr if v.get('all_pass')),
                               fails={k: sum(1 for v in rr if (v.get('tests') or {}).get(k) is False)
                                      for k in ('X1', 'bass_gap', 'V1', 'outgoing_fader_tail', 'L1', 'bass_never_doubles', 'N1')},
                               dip_med=med([v.get('dip') for v in rr]), pcol_med=sp('pcol'), pcty_med=sp('pcty'),
                               banger_med=sp('banger_clash_rate'), designed_tail24_med=med([v.get('designed_tail24') for v in rr]))
        allres[var] = dict(rows=res, summary=summ)
        json.dump(allres[var], open(os.path.join(paths.RESULTS, f'eval_tailexit_{var}.json'), 'w'), indent=1, default=str)
        print('SUMMARY', var, json.dumps(summ), flush=True)
    return allres


if __name__ == '__main__':
    main(sys.argv[1:])
