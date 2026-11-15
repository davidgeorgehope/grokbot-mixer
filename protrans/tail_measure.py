#!/usr/bin/env python3
"""Outgoing-tail length (2026-11-15 TAIL_EXIT research).

Per admitted pair, on the mix audio (pro clip, or our render of the same pair) with the scorer's own
NNLS deck gains (score.source_gain_events path: diagnose_gap.band_gains on version-located sources):
  swap  = scorer bass_swap event (bass-band deck gains, events_from_pair)
  end_T = the outgoing's final sustained exit under T dB relative to its own 90th-percentile all-band gain
          (last bar above T, +1), T in -12 (the scorer's outgoing_cut), -20, -24 (the calibration "gone" line), -30
  tail_T = end_T - swap, in bars (174 BPM). Censored (not counted) when the outgoing is still above T at the
          clip end, or the swap is undetected.
For our renders it also reads the designed tail from the meta: bars from the low-lane swap end to the
outgoing fader under -30 dB.
NNLS fits a muted deck at roughly -7..-12 dB (PROCESS.md), so the -30 dB threshold is often never reached
on audio; n is reported per threshold.
Usage: python3 protrans/tail_measure.py <variant> [<variant> ...]  -> results/tail_measure_<variant>.json
"""
import json, os, sys, glob
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths, score
import run_admitted_tune as T

THR = (-12, -20, -24, -30)


def curves(mix_path, sa, sb):
    import diagnose_gap as D
    mix = score._load(mix_path)
    aligned = []
    for p in (sa, sb):
        loc = D.version_match.locate_in(mix, score._load(p))
        if loc.get('track_t') is None:
            return None
        y = D.place_source(p, loc['track_t'], loc['mix_t'], len(mix))
        y, _ = D.refine_lag(mix, y)
        aligned.append(y)
    gains, _, times, _ = D.band_gains(mix, *aligned)
    t = np.arange(len(score._rms(mix))) * score.HOP / score.SR
    c = lambda band, deck: score._db(np.interp(t, times, gains[band][deck]))
    return dict(bass=(c('bass', 'a'), c('bass', 'b')), all=(c('all', 'a'), c('all', 'b')))


def tails(cv):
    ev = score.events_from_pair(*cv['bass'])
    swap = ev['bass_swap']
    o = score._to_bars(cv['all'][0]); o = o - np.percentile(o, 90)
    out = dict(swap=swap, n_bars=int(len(o)))
    for T_ in THR:
        act = np.flatnonzero(o > T_)
        end = int(act[-1]) + 1 if len(act) else 0
        out[f'end{-T_}'] = end if end < len(o) else None
        out[f'tail{-T_}'] = (end - swap) if (swap is not None and end < len(o)) else None
    return out


def designed(meta_path):
    try:
        M = json.load(open(meta_path))
    except Exception:
        return None
    t = M['trans'][0]
    if not t.get('bass_swap'):
        return None
    xs = np.array(t['xfader'], float)
    g = 20 * np.log10(np.cos(xs[:, 1] * np.pi / 2) + 1e-9)
    k = np.flatnonzero(g <= -30)
    gone = float(xs[k[0], 0]) if len(k) else float(xs[-1, 0])
    return dict(swap_end=float(t['bass_swap'][1]), gone30=gone, tail30=round(gone - float(t['bass_swap'][1]), 3),
                X=float(t['end_bar'] - t['start_bar']), tail_exit=t.get('tail_exit'))


def stats(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return dict(n=0)
    a = np.array(xs, float)
    q1, med, q3 = np.percentile(a, [25, 50, 75])
    return dict(n=len(a), median=round(float(med), 2), q1=round(float(q1), 2), q3=round(float(q3), 2),
                iqr=round(float(q3 - q1), 2), mean=round(float(a.mean()), 2))


def main(variants):
    recs = {r['id']: r for r in T.load_recs()}
    pro_cache = os.path.join(paths.RESULTS, 'tail_measure_pro.json')
    pro = json.load(open(pro_cache)) if os.path.exists(pro_cache) else {}
    for rid, rec in recs.items():
        if rid in pro:
            continue
        sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a'); sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
        try:
            cv = curves(rec['pro_clip'], sa, sb)
            pro[rid] = dict(split=rec['split'], **(tails(cv) if cv else dict(error='locate failed')))
        except Exception as e:
            pro[rid] = dict(split=rec['split'], error=f'{type(e).__name__}: {e}'[-200:])
        print('pro', rid, pro[rid], flush=True)
        json.dump(pro, open(pro_cache, 'w'), indent=1)
    out = dict(pro=pro, pro_stats={f'tail{-t}': stats([v.get(f'tail{-t}') for v in pro.values()]) for t in THR})
    for var in variants:
        rows = T.load_ckpt(var)
        res = {}
        for rid, row in rows.items():
            rec = recs.get(rid)
            if not rec or not row.get('ours') or not os.path.exists(row['ours']):
                continue
            sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a'); sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
            base = os.path.splitext(row['ours'])[0]
            metas = glob.glob(base + '_*_meta.json')
            try:
                cv = curves(row['ours'], sa, sb)
                res[rid] = dict(split=rec['split'], **(tails(cv) if cv else dict(error='locate failed')))
            except Exception as e:
                res[rid] = dict(split=rec['split'], error=f'{type(e).__name__}: {e}'[-200:])
            res[rid]['designed'] = designed(metas[0]) if metas else None
            print(var, rid, res[rid].get('tail12'), res[rid].get('tail20'), res[rid].get('tail30'),
                  (res[rid]['designed'] or {}).get('tail30'), flush=True)
        st = {f'tail{-t}': stats([v.get(f'tail{-t}') for v in res.values()]) for t in THR}
        st['designed_tail30'] = stats([(v.get('designed') or {}).get('tail30') for v in res.values()])
        out[var] = dict(rows=res, stats=st)
        json.dump(dict(rows=res, stats=st), open(os.path.join(paths.RESULTS, f'tail_measure_{var}.json'), 'w'), indent=1)
    print('STATS ' + json.dumps({k: (v['stats'] if isinstance(v, dict) and 'stats' in v else v)
                                  for k, v in out.items() if k != 'pro'}), flush=True)
    return out


if __name__ == '__main__':
    main(sys.argv[1:])
