"""Diagnostic only (2026-11-20 BASS_FILL): re-score a variant's renders with the scorer's clip alignment PINNED to the
baseline's lag for the same pair. The official scorer picks its own lag from kick-envelope correlation; adding the
incoming's drop bass (kick fundamentals < 150 Hz) under its intro can move that lag by bars, which then misaligns every
curve. Same window, same snippet => the baseline lag is the like-for-like alignment. Official numbers stay the primary
result; this is reported next to them. Usage: python3 protrans/rescore_pinned_bf.py <base_variant> <variant>"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths, score as S, run_admitted_tune as T
base, var = sys.argv[1], sys.argv[2]
B = T.load_ckpt(base); V = T.load_ckpt(var); recs = {r['id']: r for r in T.load_recs()}
_orig = S.align_ours_to_pro
out = {}
for rid, row in V.items():
    if rid not in B or 'score' not in row or 'score' not in B[rid]: continue
    lag = int(B[rid]['score']['breakdown']['align']['lag_samples']); rec = recs[rid]
    def pinned(y_pro, y_ours, sr=S.SR, max_shift_s=None, _lag=lag):
        yp, yo = (y_pro[_lag:], y_ours) if _lag >= 0 else (y_pro, y_ours[-_lag:])
        n = min(len(yp), len(yo)); return yp[:n], yo[:n], _lag, 0.0
    S.align_ours_to_pro = pinned
    try:
        sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a'); sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
        sc = S.score(rec['pro_clip'], row['ours'], src_a=sa, src_b=sb, use_demucs=False, cache=paths.CACHE)
        sb_ = S.score(rec['pro_clip'], B[rid]['ours'], src_a=sa, src_b=sb, use_demucs=False, cache=paths.CACHE)
    finally:
        S.align_ours_to_pro = _orig
    out[rid] = dict(split=rec['split'], base_official=B[rid]['score']['score'], var_official=row['score']['score'],
                    base_pinned=sb_['score'], var_pinned=sc['score'], lag_base=lag, lag_var_official=row['score']['breakdown']['align']['lag_samples'])
    print(rid, out[rid], flush=True)
m = lambda xs: round(sum(xs) / len(xs), 2) if xs else None
summ = {sp: {k: m([v[k] for v in out.values() if v['split'] == sp]) for k in ('base_official', 'var_official', 'base_pinned', 'var_pinned')} for sp in ('train', 'test')}
json.dump(dict(rows=out, summary=summ), open(os.path.join(paths.RESULTS, f'pinned_{var}_vs_{base}.json'), 'w'), indent=1)
print('PINNED ' + json.dumps(summ), flush=True)
