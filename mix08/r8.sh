#!/usr/bin/env bash
# r8: same 46-track crate, SOFT=0, DROP_FRAC=0.333. Beam now ranks hard drop/outro
# deficit before cost, so BW's bob16 warning cannot evict on-pace drop paths.
# Remaining-blend bound uses 64 bars per added track (was 32). Tests unchanged.
unset PSKILL PSDBG
cd /workspace/mixes/src2
SOFT=0 DROP_FRAC=0.333 bash ../mix08/search.sh plan_mix08_r8.json
