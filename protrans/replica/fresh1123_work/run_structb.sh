#!/bin/bash
# STRUCTB=0 ablation on the 19 scored fresh-1123 pairs plus joe_syntax_hospital__13.
# STRUCTB is the outro-over-intro bonus only; STRUCTW guards stay at 300.
# Does not write rules.json. Does not clean /tmp/protrans*. Not a promotion eval.
set -euo pipefail
cd /workspace/mixes/protrans || exit 1
FW=/workspace/mixes/protrans/replica/fresh_work_1123
export GATE_FEAT=$FW/features GATE_FLIB=$FW/lib EXTRA_SRC=$FW/lib
export TALK_THREADS="${TALK_THREADS:-2}"
export WORKERS="${WORKERS:-2}"
export ONLY="${ONLY:-yolowich_FIdBhH3SuXk,nicky_havey_1xpuWyKZ4R0,outer_bass_3Tt7qDw8uaQ,joe_syntax_hospital__13}"
ONLY="$ONLY" WORKERS="$WORKERS" python3 replica/eval_gate.py \
  "fstrb01123={\"STRUCTB\":0}" || exit 2
python3 replica/fresh1123_structb_eval.py || exit 3
