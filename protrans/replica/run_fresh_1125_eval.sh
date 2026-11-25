#!/usr/bin/env bash
set -euo pipefail
cd /workspace/mixes/protrans
FW=/workspace/mixes/protrans/replica/fresh_work_1125
export GATE_FEAT=$FW/features GATE_FLIB=$FW/lib EXTRA_SRC=$FW/lib
export TALK_THREADS=2 WORKERS=2
export ONLY=zaklynskyi_SKL2rC3tcug,eidan_J5bKdjl2xKo
python3 replica/eval_gate.py "fdef1125={}" 'fepgk1125={"EXITPOS":1,"EXITPOS_GATE":1,"EXITPOS_DROP":1}'
python3 replica/hc2_arrays.py fdef1125 fepgk1125
python3 replica/fresh_1125_eval.py
