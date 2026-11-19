import json, os, sys, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scorer_audit import PAIRS
S = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scored_labels.json')))
COMPS = ['score', 'score_v2', 'stem_curves', 'deck_curves', 'beat_align', 'bass_swap', 'outgoing_cut', 'blend_length', 'beat_identity']
def val(it, c): return it.get(c) if c in ('score', 'score_v2') else (it['parts'].get(c))
def spearman(x, y):
    from scipy.stats import spearmanr; r, p = spearmanr(x, y); return round(float(r), 2), round(float(p), 3)
out = dict(items={k: dict(score=v['score'], score_v2=v['score_v2'], parts=v['parts'], rating=v.get('rating'), spotted=v.get('spotted'), note=v.get('note')) for k, v in S.items()})
# pairwise
pw = {}
for c in COMPS:
    agree = []; rows = []
    for a, b in PAIRS:
        va, vb = val(S[a], c), val(S[b], c)
        if va is None or vb is None or va == vb: rows.append((a, b, va, vb, None)); continue
        agree.append(va > vb); rows.append((a, b, va, vb, bool(va > vb)))
    pw[c] = dict(agree=int(sum(agree)), n=len(agree), rows=rows)
out['pairwise'] = pw
# blind tests
daily = [v for k, v in S.items() if k.startswith('daily_')]
rated = [v for v in daily if v.get('rating') is not None]
out['blind_rating_spearman'] = {c: spearman([val(v, c) for v in rated], [v['rating'] for v in rated]) for c in COMPS if all(val(v, c) is not None for v in rated)}
sp = [v for v in daily if v.get('spotted')]; ns = [v for v in daily if v.get('spotted') is False]
out['blind_spotted'] = {c: dict(spotted_mean=round(float(np.mean([val(v, c) for v in sp if val(v, c) is not None])), 2),
                                fooled_or_unsure_mean=round(float(np.mean([val(v, c) for v in ns if val(v, c) is not None])), 2)) for c in COMPS}
out['n'] = dict(daily=len(daily), rated=len(rated), spotted=len(sp), not_spotted=len(ns), pairs=len(PAIRS))
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'analysis.json'), 'w'), indent=1)
print(json.dumps(out['n']))
for c in COMPS: print(f"{c:13s} pairwise {pw[c]['agree']}/{pw[c]['n']}  rating rho {out['blind_rating_spearman'].get(c)}  spotted {out['blind_spotted'][c]}")
print()
for a, b, va, vb, ok in pw['score']['rows']: print(f'{a:18s} > {b:18s} score {va} vs {vb} agree={ok}')
print()
for v in sorted(daily, key=lambda v: v['id']): print(v['id'], v.get('rating'), v.get('spotted'), v['score'], {k: v['parts'][k] for k in ('stem_curves','deck_curves','beat_align','bass_swap','outgoing_cut','blend_length')})
