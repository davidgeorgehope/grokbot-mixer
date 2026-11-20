#!/bin/bash
# 2026-11-20 nightly: Sirenity fresh mix (isolated fresh_work_1120) - render default + the three frozen epg candidates, cache HC arrays, compare.
cd /workspace/mixes/protrans || exit 1
FW=/workspace/mixes/protrans/replica/fresh_work_1120
export GATE_FEAT=$FW/features GATE_FLIB=$FW/lib EXTRA_SRC=$FW/lib
ONLY=sirenity_ofcHup56lME WORKERS=${WORKERS:-2} python3 replica/eval_gate.py "fdef1120={}" 'fepgs1120={"EXITPOS":1,"EXITPOS_GATE":1}' 'fepgd1120={"EXITPOS":1,"EXITPOS_DROP":1}' 'fepgk1120={"EXITPOS":1,"EXITPOS_GATE":1,"EXITPOS_DROP":1}' || exit 2
python3 replica/hc2_arrays.py fdef1120 fepgs1120 fepgd1120 fepgk1120 || exit 3
python3 replica/fresh1120_eval.py || exit 4
