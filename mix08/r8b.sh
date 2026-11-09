#!/usr/bin/env bash
# r8b: same search as r8 (378 table-feasible in r8 before dry crashed).
# Stem cache writes are now unique-temp + thread/process locked; dry-verify
# catches exceptions so one cache miss can't abort the pool; table-feasible
# plans are dumped to plan_mix08_r8b.pool.json. Longer dry budget in case a
# couple of drums+bass stems need rebuilding (cleanup removed most .dnb.wav).
unset PSKILL PSDBG
cd /workspace/mixes/src2
SOFT=0 DROP_FRAC=0.333 DRY_BUDGET_S=7200 bash ../mix08/search.sh plan_mix08_r8b.json
