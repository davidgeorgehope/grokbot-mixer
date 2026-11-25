"""MID_HOLD research (2026-11-25): incoming per-band deck gains (fader x EQ, NNLS like corpus_v2 deck_levels) in the pro
clip vs our renders, per variant checkpoint. Reports, per clip: incoming mids minus highs (dB) before the incoming bass
reaches full level, and mids-arrival minus bass-arrival (bars). Read-only. Usage: bandlag.py <variant> [...]"""
import json, os, sys, numpy as np
sys.path.insert(0, '/workspace/mixes/protrans')
import paths, score, diagnose_gap as D, run_admitted_tune as T
import corpus_v2_pipeline as CP

def levels(clip, sa, sb):
    mix = score._load(clip); al = []
    for p in (sa, sb):
        loc = D.version_match.locate_in(mix, score._load(p))
        if loc.get('track_t') is None: return None
        y = D.place_source(p, loc['track_t'], loc['mix_t'], len(mix)); y, _ = D.refine_lag(mix, y); al.append(y)
    gains, _, times, hop = D.band_gains(mix, *al)
    return CP.per_bar_deck_levels(gains, hop, D)

def stats(dl):
    B = {k: np.array(dl[k]['b'], float) for k in ('all', 'bass', 'mids', 'highs')}
    n = min(len(v) for v in B.values())
    if n < 12: return None
    def arr(x, thr=3):
        ref = np.percentile(x[-max(4, n // 4):], 50)
        if ref < -20: return None
        for i in np.where(x >= ref - thr)[0]:
            if i + 1 < n and x[i + 1] >= ref - thr: return int(i)
        return None
    def aud(x):
        ref = np.percentile(x[-max(4, n // 4):], 50); ok = np.where(x >= ref - 18)[0]; return int(ok[0]) if len(ok) else None
    a = {k: arr(B[k]) for k in B}; s = aud(B['all'])
    if None in a.values() or s is None: return None
    early = float(np.median(B['mids'][s:a['bass']] - B['highs'][s:a['bass']])) if a['bass'] - s >= 2 else None
    early_mid = float(np.median(B['mids'][s:a['bass']] - np.percentile(B['mids'][-max(4, n // 4):], 50))) if a['bass'] - s >= 2 else None
    return dict(mid_minus_bass=a['mids'] - a['bass'], early_mid_minus_high=early, early_mid_vs_full=early_mid)

out = {}
recs = {r['id']: r for r in T.load_recs()}
for v in sys.argv[1:]:
    ck = T.load_ckpt(v); res = {}
    for rid, row in ck.items():
        rec = recs[rid]; sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a'); sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
        try:
            res[rid] = dict(ours=stats(levels(row['ours'], sa, sb) or {}) if row.get('ours') else None)
            if v == sys.argv[1]: res[rid]['pro'] = stats(levels(rec['pro_clip'], sa, sb) or {})
        except Exception as e:
            res[rid] = dict(error=str(e)[-200:])
        print(v, rid, res[rid], flush=True)
    out[v] = res
json.dump(out, open('/workspace/mixes/protrans/research_1125/bandlag.json', 'w'), indent=1, default=float)
def summ(key, who, v):
    xs = [r[who][key] for r in out[v].values() if r.get(who) and r[who].get(key) is not None]
    return (len(xs), round(float(np.median(xs)), 2) if xs else None)
for v in out:
    for who in (['pro', 'ours'] if v == sys.argv[1] else ['ours']):
        print('SUMMARY', v, who, {k: summ(k, who, v) for k in ('mid_minus_bass', 'early_mid_minus_high', 'early_mid_vs_full')})
