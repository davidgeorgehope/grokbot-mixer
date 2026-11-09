#!/usr/bin/env bash
# r4: same 42-track crate as r3, but do not require the Lilies>JHO pair (PINW still preferred if chosen).
unset PSKILL PSDBG
cd /workspace/mixes/src2
SOFT=1 DROP_FRAC=0.2 bash ../mix08/search.sh plan_mix08_r4.json
