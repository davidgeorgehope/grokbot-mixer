"""Prototype eval: decision-level match of each labelled clip to the pro (same extractor as replica/extract_protrans.py)."""
import json, os, sys
H = os.path.dirname(os.path.abspath(__file__)); P = os.path.dirname(H); sys.path.insert(0, P); sys.path.insert(0, os.path.join(P, 'replica'))
import extract_protrans as X
import run_admitted_tune as T
S = json.load(open(os.path.join(H, 'scored_labels.json')))
PRO = json.load(open(os.path.join(P, 'replica', 'protrans_decisions.json')))
recs = {r['id']: r for r in T.load_recs()}
OUT = os.path.join(H, 'decision_match.json')
done = json.load(open(OUT)) if os.path.exists(OUT) else {}
for k, it in S.items():
    if k in done: continue
    rec = dict(recs[it['pick']]); rec['pro_clip'] = it['clip']
    try: d = X.run_one(rec)
    except Exception as e: d = dict(error=repr(e)[-300:])
    p = PRO[it['pick']]
    keys = ('out_left_at_entry', 'in_bar_at_entry', 'overlap_bars', 'swap_after_entry')
    diff = {kk: (None if d.get(kk) is None or p.get(kk) is None else round(abs(float(d[kk]) - float(p[kk])), 1)) for kk in keys}
    done[k] = dict(ours={kk: d.get(kk) for kk in keys}, pro={kk: p.get(kk) for kk in keys}, diff=diff, error=d.get('error'))
    json.dump(done, open(OUT, 'w'), indent=1, default=str)
    print(k, done[k]['ours'], 'diff', diff, flush=True)
