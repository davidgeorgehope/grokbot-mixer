"""n1121: nightly_hill_climb.py unchanged, except (1) final shared-scratch cleanup deferred (other agents' jobs
use /tmp/protrans*), (2) 2 render workers instead of 4 (box had ~2.4 GB free RAM; avoid OOM-killing other jobs).

Vetoed-pair count and breakdown-exit share for dclash arms are logged by
nightly_hill_climb.py via dclash_report.py (added 2026-11-23). n1121 itself
finished before that hook; see replica/n1121_dclash_share.json for the
retroactive counts from its score checkpoints.
"""
import sys, os, functools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cleanup, nightly_hill_climb as N, run_admitted_tune as T
cleanup.drop_stems = lambda: print('drop_stems deferred (shared scratch in use by other jobs)', flush=True)
_orig = T.run_set_checkpointed
T.run_set_checkpointed = lambda recs, rules, variant, tag, workers=2: _orig(recs, rules, variant, tag, workers=2)
N.main()
