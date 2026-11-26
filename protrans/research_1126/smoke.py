"""HIGH_GATE smoke (2026-11-26 research): one pair, base vs HIGH_GATE=1, render+score. rules.json untouched."""
import json, sys
sys.path.insert(0, '/workspace/mixes/protrans')
import run_admitted_tune as T, paths
pid = sys.argv[1]
recs = [r for r in T.load_recs() if r['id'] == pid]
rules = json.load(open(paths.RULES)); assert not rules.get('HIGH_GATE')
for name, rr in (('hgsb1126', rules), ('hgs1126', dict(rules, HIGH_GATE=1))):
    rows = T.run_set_checkpointed(recs, rr, name, name[:6], workers=1)
    r = rows[0]; print('SMOKE', name, r.get('error') or (r['score']['score'], r['pick'], r['ours']), flush=True)
