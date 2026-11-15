#!/usr/bin/env python3
"""Per-bar outgoing level curves (2026-11-15 TAIL_EXIT research).

Same NNLS deck-gain path as tail_measure.py (diagnose_gap.band_gains on version-located
sources). Saves the outgoing all-band curve, relative to its 90th percentile, aligned to
the scorer bass-swap and to the clip start, plus designed fader curves for our renders.

Usage: python3 protrans/tail_curves.py <variant> [<variant> ...]
  writes results/tail_curves_<variant>.json and prints median curves vs the cached pro.
"""
import json, os, sys, glob
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths, score
import run_admitted_tune as T
import tail_measure as TM

ZONES = dict(loud=(-6, 99), audible=(-18, -6), residual=(-30, -18))


def bar_curve(cv):
    """outgoing/incoming all-band dB, raw and relative to outgoing p90, plus bass-swap."""
    ev = score.events_from_pair(*cv['bass'])
    raw = score._to_bars(cv['all'][0])  # outgoing = deck a
    inc = score._to_bars(cv['all'][1])
    p90 = float(np.percentile(raw, 90))
    rel = raw - p90
    inc_rel = inc - float(np.percentile(inc, 90))
    return dict(swap=ev['bass_swap'], n_bars=int(len(raw)), p90=round(p90, 2),
                out_raw=[round(float(x), 2) for x in raw],
                out_rel=[round(float(x), 2) for x in rel],
                in_rel=[round(float(x), 2) for x in inc_rel])


def zone_bars(rel, swap, lo, hi):
    rel = np.asarray(rel, float)
    n = len(rel)
    i0 = 0 if swap is None else max(0, int(swap))
    return int(np.sum((rel[i0:] > lo) & (rel[i0:] <= hi)))


def aligned(rel, swap, lo=-8, hi=16):
    """outgoing rel-dB from swap+lo to swap+hi; None where off-clip."""
    rel = np.asarray(rel, float)
    out = []
    for k in range(lo, hi + 1):
        i = (None if swap is None else int(swap) + k)
        out.append(None if (i is None or i < 0 or i >= len(rel)) else float(rel[i]))
    return out


def summ(cvrow):
    rel = cvrow['out_rel']
    sw = cvrow['swap']
    s = {f'after_{name}': zone_bars(rel, sw, lo, hi) for name, (lo, hi) in ZONES.items()}
    s['after_silent'] = zone_bars(rel, sw, -999, -30) if sw is not None else None
    s['n_bars'] = cvrow['n_bars']
    s['swap'] = sw
    s['aligned'] = aligned(rel, sw)
    # level at key offsets
    al = s['aligned']
    for name, idx in (('at_swap', 8), ('p2', 10), ('p4', 12), ('p8', 16)):  # lo=-8 so 0 is index 8
        s[name] = al[idx] if idx < len(al) else None
    return s


def med_curve(rows, key='aligned'):
    # list of lists with Nones
    arrs = [r[key] for r in rows if r.get(key)]
    if not arrs:
        return []
    w = max(len(a) for a in arrs)
    out = []
    for i in range(w):
        xs = [a[i] for a in arrs if i < len(a) and a[i] is not None]
        if not xs:
            out.append(None)
        else:
            q1, med, q3 = np.percentile(xs, [25, 50, 75])
            out.append(dict(n=len(xs), med=round(float(med), 2),
                            q1=round(float(q1), 2), q3=round(float(q3), 2)))
    return out


def stats(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return dict(n=0)
    a = np.array(xs, float)
    q1, med, q3 = np.percentile(a, [25, 50, 75])
    return dict(n=len(a), median=round(float(med), 2), q1=round(float(q1), 2),
                q3=round(float(q3), 2), mean=round(float(a.mean()), 2))


def one_mix(mix_path, sa, sb, meta_path=None):
    cv = TM.curves(mix_path, sa, sb)
    if not cv:
        return dict(error='locate failed')
    row = bar_curve(cv)
    row['sum'] = summ(row)
    if meta_path:
        row['designed'] = TM.designed(meta_path)
    return row


def main(variants):
    recs = {r['id']: r for r in T.load_recs()}
    pro_path = os.path.join(paths.RESULTS, 'tail_curves_pro.json')
    pro = json.load(open(pro_path)) if os.path.exists(pro_path) else {}
    for rid, rec in recs.items():
        if rid in pro and 'out_rel' in pro[rid]:
            continue
        sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a')
        sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
        try:
            row = one_mix(rec['pro_clip'], sa, sb)
        except Exception as e:
            row = dict(error=f'{type(e).__name__}: {e}'[-200:])
        row['split'] = rec['split']
        pro[rid] = row
        print('pro', rid, row.get('error') or row['sum'], flush=True)
        json.dump(pro, open(pro_path, 'w'))
    pro_sums = [v['sum'] for v in pro.values() if v.get('sum')]
    pro_agg = dict(
        n=len(pro_sums),
        after_loud=stats([s['after_loud'] for s in pro_sums]),
        after_audible=stats([s['after_audible'] for s in pro_sums]),
        after_residual=stats([s['after_residual'] for s in pro_sums]),
        at_swap=stats([s['at_swap'] for s in pro_sums]),
        p2=stats([s['p2'] for s in pro_sums]),
        p4=stats([s['p4'] for s in pro_sums]),
        p8=stats([s['p8'] for s in pro_sums]),
        aligned=med_curve(pro_sums),
    )
    print('PRO_AGG ' + json.dumps({k: v for k, v in pro_agg.items() if k != 'aligned'}), flush=True)
    print('PRO_CURVE swap-8..+16 ' + json.dumps(pro_agg['aligned']), flush=True)

    for var in variants:
        rows = T.load_ckpt(var)
        res = {}
        for rid, row in rows.items():
            rec = recs.get(rid)
            if not rec or not row.get('ours') or not os.path.exists(row['ours']):
                continue
            sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a')
            sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
            base = os.path.splitext(row['ours'])[0]
            metas = [m for m in glob.glob(base + '_*_meta.json') if not m.endswith('_dry_meta.json')]
            try:
                r = one_mix(row['ours'], sa, sb, metas[0] if metas else None)
            except Exception as e:
                r = dict(error=f'{type(e).__name__}: {e}'[-200:])
            r['split'] = rec['split']
            res[rid] = r
            print(var, rid, r.get('error') or r['sum'], flush=True)
        sums = [v['sum'] for v in res.values() if v.get('sum')]
        agg = dict(
            n=len(sums),
            after_loud=stats([s['after_loud'] for s in sums]),
            after_audible=stats([s['after_audible'] for s in sums]),
            after_residual=stats([s['after_residual'] for s in sums]),
            at_swap=stats([s['at_swap'] for s in sums]),
            p2=stats([s['p2'] for s in sums]),
            p4=stats([s['p4'] for s in sums]),
            p8=stats([s['p8'] for s in sums]),
            aligned=med_curve(sums),
        )
        out = dict(rows=res, agg=agg)
        json.dump(out, open(os.path.join(paths.RESULTS, f'tail_curves_{var}.json'), 'w'))
        print('AGG ' + var + ' ' + json.dumps({k: v for k, v in agg.items() if k != 'aligned'}), flush=True)
        print('CURVE ' + var + ' ' + json.dumps(agg['aligned']), flush=True)
    return 0


if __name__ == '__main__':
    main(sys.argv[1:])
