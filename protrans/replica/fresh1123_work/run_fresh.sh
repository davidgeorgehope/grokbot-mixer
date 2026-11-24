#!/bin/bash
# Render default + the three epg candidates once for every mix isolated in
# fresh_work_1123. Does not write rules.json. Does not clean /tmp/protrans*.
set -euo pipefail
cd /workspace/mixes/protrans || exit 1
FW=/workspace/mixes/protrans/replica/fresh_work_1123
export GATE_FEAT=$FW/features GATE_FLIB=$FW/lib EXTRA_SRC=$FW/lib
export TALK_THREADS="${TALK_THREADS:-2}"
export WORKERS="${WORKERS:-2}"
# ONLY must be in the environment of eval_gate.py (a local shell var is not enough;
# without it, eval_gate falls through to frozen_ids.json and scores the 33-pair cohort).
export ONLY="${ONLY:-yolowich_FIdBhH3SuXk,nicky_havey_1xpuWyKZ4R0,outer_bass_3Tt7qDw8uaQ}"
ONLY="$ONLY" WORKERS="$WORKERS" python3 replica/eval_gate.py   "fdef1123={}"   'fepgs1123={"EXITPOS":1,"EXITPOS_GATE":1}'   'fepgd1123={"EXITPOS":1,"EXITPOS_DROP":1}'   'fepgk1123={"EXITPOS":1,"EXITPOS_GATE":1,"EXITPOS_DROP":1}' || exit 2
python3 replica/hc2_arrays.py fdef1123 fepgs1123 fepgd1123 fepgk1123 || exit 3
python3 replica/fresh1123_eval.py || exit 4
