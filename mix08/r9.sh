#!/usr/bin/env bash
# r9: same 46-track crate and tests as r8b. Planner now refuses any 8+ bar
# drums-only stretch (the actual release test), not just the incoming's first
# 8 post-blend bars. predict() no longer treats bob16/x32 warnings as all_ok
# fails. Pool dump and dry-verify budget unchanged.
unset PSKILL PSDBG
cd /workspace/mixes/src2
SOFT=0 DROP_FRAC=0.333 DRY_BUDGET_S=7200 bash ../mix08/search.sh plan_mix08_r9.json
