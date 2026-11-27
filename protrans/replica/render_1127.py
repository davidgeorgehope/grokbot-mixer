"""n1127: render a drum-clash candidate arm on the official 33 protrans pairs on top of the CURRENT default (ridegate, rules.json as is)
using a COPY of rules.json with the arm's flags; rules.json is never written. Checkpoint variant n1127_<arm>, tag prefix n27<x> in
/tmp/protrans_bench (own prefix). Then prints DCLASH_COUNTS vs the default cohort lcb_1127 (dclash_report) and flags a regression if
breakdown exits spread to non-vetoed pairs. usage: render_1127.py <arm> <tag>"""
import json, os, sys
H = os.path.dirname(os.path.abspath(__file__)); P0 = os.path.dirname(H); sys.path.insert(0, H); sys.path.insert(0, P0)
import paths, run_admitted_tune as T, dclash_report as DC
ARMS = {'dclash_land6': {'DRUMCLASH': 1, 'DRUMCLASH_RISK': 1, 'DRUMCLASH_LAND': 1},
        'dclash_land7': {'DRUMCLASH': 1, 'DRUMCLASH_RISK': 1, 'DRUMCLASH_LAND': 1, 'PLAN_LAND': 1}}
arm, tag = sys.argv[1], sys.argv[2]; W = os.path.join(H, 'nightly_1127_work')
rules = json.load(open(paths.RULES)); assert rules.get('RIDEGATE'), 'expected ridegate default'
rules = dict(rules, **ARMS[arm]); json.dump(rules, open(os.path.join(W, f'rules_{arm}.json'), 'w'), indent=1)
rows = T.run_set_checkpointed(T.load_recs(), rules, f'n1127_{arm}', tag, workers=int(os.environ.get('WORKERS', 3)))
base = list(T.load_ckpt('lcb_1127').values())
r = DC.summarize(rows, base); spread = sorted(set(r['breakdown_exit_ids']) - set(r['vetoed_ids'])); r['regression_breakdown_spread_to_nonvetoed'] = spread
print(f"DCLASH_COUNTS arm={arm} pairs={r['n']} vetoed={r['vetoed']} breakdown_exits={r['breakdown_exits']} base_breakdown_exits={r['base_breakdown_exits']} "
      f"REGRESSION={'YES ' + str(spread) if spread else 'no'}", flush=True)
json.dump(r, open(os.path.join(W, f'dclash_{arm}.json'), 'w'), indent=1, default=str)
