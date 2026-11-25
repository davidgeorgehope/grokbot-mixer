"""MID_HOLD smoke (2026-11-25 research): one pair, base vs MID_HOLD=1, render+score. rules.json untouched."""
import json, sys, os
sys.path.insert(0, '/workspace/mixes/protrans')
import run_admitted_tune as T, paths
pid = sys.argv[1]; db = sys.argv[2] if len(sys.argv) > 2 else '6'
recs = [r for r in T.load_recs() if r['id'] == pid]
rules = json.load(open(paths.RULES)); assert not rules.get('MID_HOLD')
for name, rr in (('mhsb1125', rules), (f'mhs{db}_1125', dict(rules, MID_HOLD=1, MID_HOLD_DB=float(db)))):
    rows = T.run_set_checkpointed(recs, rr, name, name[:6], workers=1)
    r = rows[0]; print('SMOKE', name, r.get('error') or (r['score']['score'], r['pick'], r['ours']), flush=True)
