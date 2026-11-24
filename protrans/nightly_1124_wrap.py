"""n1124: nightly_hill_climb.py unchanged (card = replica/nightly_candidates.json, 6 arms) except
(1) shared-scratch cleanup deferred (other agents use /tmp/protrans*), (2) 3 render workers.
DRUMCLASH arms log vetoed-pair count and breakdown-exit share vs default via dclash_report.py (in the job log);
the wrapper also writes replica/n1124_dclash_share.json and flags a regression if breakdown exits spread to non-vetoed pairs."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cleanup, nightly_hill_climb as N, run_admitted_tune as T
cleanup.drop_stems = lambda: print('drop_stems deferred (shared scratch in use by other jobs)', flush=True)
_orig = T.run_set_checkpointed
T.run_set_checkpointed = lambda recs, rules, variant, tag, workers=3: _orig(recs, rules, variant, tag, workers=3)
import dclash_report as DC
_ds = DC.summarize; _acc = {}
def _wrapped(arm_rows, base_rows=None):
    r = _ds(arm_rows, base_rows)
    spread = sorted(set(r['breakdown_exit_ids']) - set(r['vetoed_ids']))
    r['regression_breakdown_spread_to_nonvetoed'] = spread
    print(f"DCLASH_COUNTS pairs={r['n']} vetoed={r['vetoed']} breakdown_exits={r['breakdown_exits']} "
          f"base_breakdown_exits={r.get('base_breakdown_exits')} REGRESSION={'YES '+str(spread) if spread else 'no'}", flush=True)
    _acc[len(_acc)] = r
    json.dump(_acc, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'replica', 'n1124_dclash_share.json'), 'w'), indent=1, default=str)
    return r
DC.summarize = _wrapped
N.DC = DC
N.main()
