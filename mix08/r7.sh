#!/usr/bin/env bash
# r7: same 46-track crate as r6. Search hard-gates now match the release tests:
# drop_end, outro, coverage, beatless, variety stay hard; x32/bob16 >= half are warnings
# (the listener 2026-11-01) and only costs, not dry-verify filters. Open-any also prunes
# paths that cannot reach drop/outro even if every remaining blend hits them.
unset PSKILL PSDBG
cd /workspace/mixes/src2
SOFT=0 DROP_FRAC=0.333 bash ../mix08/search.sh plan_mix08_r7.json
