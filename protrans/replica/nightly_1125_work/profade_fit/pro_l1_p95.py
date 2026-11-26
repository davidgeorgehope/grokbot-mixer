#!/usr/bin/env python3
"""Measure L1 / l1a on the 33 pinned pro clips (read-only). Same maths as pro_fade_fit, 120 Hz lows.
Does not change any threshold. Writes profade_fit/pro_l1_p95.json."""
import json, os, sys, time
import numpy as np
os.environ.setdefault('PROTRANS_SRC2', '/workspace/mixes/src2_pin_n1121')
sys.path.insert(0, '/workspace/mixes/protrans')
sys.path.insert(0, '/workspace/mixes/protrans/replica')
sys.path.insert(0, os.environ['PROTRANS_SRC2'])
import paths, run_admitted_tune as T, score, diagnose_gap as D, blend_diag as BD
from engine import BS

OUT = '/workspace/mixes/protrans/replica/nightly_1125_work/profade_fit/pro_l1_p95.json'
PRO = json.load(open('/workspace/mixes/protrans/replica/protrans_decisions.json'))
HOP = 0.25


def stereo(y):
    y = np.asarray(y, float)
    if y.ndim == 1:
        return np.stack([y, y], 1)
    return y


def measure(rec, d):
    s, e = d.get('in_entry_clip_bar'), d.get('out_gone_clip_bar')
    if s is None or e is None or e - s < 4:
        return None
    y = score._load(rec['pro_clip'])
    y1 = y.mean(1) if getattr(y, 'ndim', 1) > 1 else y
    sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a')
    sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
    za = D.place_source(sa, d['loc']['a']['track_t'], d['loc']['a']['mix_t'], len(y1)); za, _ = D.refine_lag(y1, za)
    zb = D.place_source(sb, d['loc']['b']['track_t'], d['loc']['b']['mix_t'], len(y1)); zb, _ = D.refine_lag(y1, zb)
    g, rec_w, tt, hop = D.band_gains(y1, za, zb, hop_s=HOP)
    n = min(len(y1), len(za), len(zb))
    ts = np.arange(n) / score.SR
    # Reconstruct each deck from per-band NNLS gains (no +/-4 dB clip)
    A = np.zeros(n, np.float32); B = np.zeros(n, np.float32)
    pb = D.split_bands(za[:n]); qb = D.split_bands(zb[:n])
    for k in pb:
        ga = np.interp(ts, tt, g[k]['a'], left=g[k]['a'][0], right=g[k]['a'][-1])
        gb = np.interp(ts, tt, g[k]['b'], left=g[k]['b'][0], right=g[k]['b'][-1])
        A += (ga * pb[k]).astype(np.float32)
        B += (gb * qb[k]).astype(np.float32)
    y2, A2, B2 = stereo(y1[:n]), stereo(A), stereo(B)
    nb = int(n // BS)
    loA = BD.band_bar_db(A2, nb, BS, 'low', 120)
    loB = BD.band_bar_db(B2, nb, BS, 'low', 120)
    sum_est = BD.band_bar_db(A2 + B2, nb, BS, 'low', 120)
    sum_mix = BD.band_bar_db(y2, nb, BS, 'low', 120)
    s = int(s); e = min(int(e), nb)
    if e - s < 4:
        return None

    def pack(sumlo, tag):
        ex = sumlo[s:e] - np.maximum(loA[s:e], loB[s:e])
        l1 = float(np.max(ex))
        refA = float(np.median(loA[:max(1, s)])) if s >= 2 else float(np.percentile(loA, 80))
        refB = float(np.median(loB[e:])) if nb - e >= 2 else float(np.percentile(loB, 80))
        aud12 = sumlo[s:e] >= max(refA, refB) - 12.0
        aud25 = sumlo[s:e] >= refA - 25.0  # official eval_graphcut audible floor
        l1a = float(np.max(ex[aud12])) if aud12.any() else 0.0
        l1_25 = float(np.max(ex[aud25])) if aud25.any() else 0.0
        k = int(np.argmax(ex))
        return dict(
            tag=tag, l1=round(l1, 2), l1_fail=l1 > 3.0,
            l1a=round(l1a, 2), l1a_fail=l1a > 3.0,
            l1_refA25=round(l1_25, 2), l1_refA25_fail=l1_25 > 3.0,
            argmax_clip_bar=int(s + k),
            loA=round(float(loA[s + k]), 1), loB=round(float(loB[s + k]), 1),
            sumlo=round(float(sumlo[s + k]), 1),
            refA=round(refA, 1), refB=round(refB, 1),
            below_body=round(float(max(refA, refB) - sumlo[s + k]), 1),
        )
    return dict(id=rec['id'], s=s, e=e, est=pack(sum_est, 'A_est+B_est'), mix=pack(sum_mix, 'pro_mix'))


def main():
    t0 = time.time(); rows = []; skipped = []
    for rec in T.load_recs():
        d = PRO.get(rec['id']) or {}
        try:
            r = measure(rec, d)
        except Exception as ex:
            skipped.append((rec['id'], type(ex).__name__, str(ex)[:160])); print('skip', rec['id'], type(ex).__name__, str(ex)[:120], flush=True); continue
        if r is None:
            skipped.append((rec['id'], 'no_overlap', '')); print('skip', rec['id'], 'no overlap', flush=True); continue
        rows.append(r)
        print('ok', rec['id'], r['est'], flush=True)
    def summ(key, field):
        v = np.array([r[key][field] for r in rows], float)
        return dict(n=len(v), p50=round(float(np.percentile(v, 50)), 2), p95=round(float(np.percentile(v, 95)), 2),
                    max=round(float(v.max()), 2), n_gt_3=int((v > 3.0).sum()),
                    ids_gt_3=[r['id'] for r in rows if r[key][field] > 3.0])
    out = dict(
        written='2026-11-26', n=len(rows), skipped=skipped, sec=round(time.time() - t0, 1),
        note='Same L1 maths as pro_fade_fit (combined <120 Hz minus the louder deck, fail > 3.0 dB). Decks are NNLS-attributed sources in the pro clip, no +/-4 dB clip. l1a = same excess only on bars whose summed lows sit within 12 dB of the louder body. l1_refA25 uses the official eval_graphcut floor (summed lows within 25 dB of outgoing body). Thresholds were not changed.',
        est=dict(l1=summ('est', 'l1'), l1a=summ('est', 'l1a'), l1_refA25=summ('est', 'l1_refA25')),
        mix=dict(l1=summ('mix', 'l1'), l1a=summ('mix', 'l1a'), l1_refA25=summ('mix', 'l1_refA25')),
        rows=rows,
    )
    json.dump(out, open(OUT, 'w'), indent=1)
    print('WROTE', OUT, json.dumps(out['est']), json.dumps(out['mix']), flush=True)


if __name__ == '__main__':
    main()
