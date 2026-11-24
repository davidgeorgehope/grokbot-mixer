#!/bin/bash
# 2026-11-23: YoloWich FIdBhH3SuXk fresh mix (isolated fresh_work_1123).
# Render default + the three epg candidates once, cache HC arrays, compare.
# Does not write rules.json. Does not clean /tmp/protrans* (corpus-v2 may use it).
set -euo pipefail
cd /workspace/mixes/protrans || exit 1
FW=/workspace/mixes/protrans/replica/fresh_work_1123
export GATE_FEAT=$FW/features GATE_FLIB=$FW/lib EXTRA_SRC=$FW/lib
export TALK_THREADS="${TALK_THREADS:-2}"
ONLY=yolowich_FIdBhH3SuXk WORKERS=${WORKERS:-2} python3 replica/eval_gate.py   "fdef1123={}"   'fepgs1123={"EXITPOS":1,"EXITPOS_GATE":1}'   'fepgd1123={"EXITPOS":1,"EXITPOS_DROP":1}'   'fepgk1123={"EXITPOS":1,"EXITPOS_GATE":1,"EXITPOS_DROP":1}' || exit 2
python3 replica/hc2_arrays.py fdef1123 fepgs1123 fepgd1123 fepgk1123 || exit 3
python3 replica/fresh1123_eval.py || exit 4
