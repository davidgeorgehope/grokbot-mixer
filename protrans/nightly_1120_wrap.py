"""n1120: run protrans/nightly_hill_climb.py unchanged, except its end-of-run cleanup.drop_stems() is deferred:
other jobs (bf-cohort-1120 diagnostics, fresh-1120 renders) may still be using /tmp/protrans* and /tmp/blend_bench.
The nightly runs that cleanup itself once nothing else is rendering."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cleanup, nightly_hill_climb as N
cleanup.drop_stems = lambda: print('drop_stems deferred (shared scratch in use by other jobs)', flush=True)
N.main()
