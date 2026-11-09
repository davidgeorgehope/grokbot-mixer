#!/usr/bin/env bash
# r5: 43-track crate (added Memory Lane 12A), SOFT=0, DROP_FRAC=1/3 to match
# test_plan_respects_outro_and_intro, no --require. PINW still preferred if chosen.
# plan_search also rejects windows that leave 8+ drums-only bars after the blend.
unset PSKILL PSDBG
cd /workspace/mixes/src2
SOFT=0 DROP_FRAC=0.333 bash ../mix08/search.sh plan_mix08_r5.json
