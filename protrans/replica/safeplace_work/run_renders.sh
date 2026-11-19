#!/bin/bash
# 2026-11-19 PLACE=safe: render rank-1 picks (sp1119<T>1), then rank-2 only where rank-1 hard-fails (sp1119<T>2). Dev only.
T=${1:-a}
cd /workspace/mixes/protrans || exit 1
W=/workspace/mixes/protrans/replica/safeplace_work
export EXTRA_SRC=/workspace/mixes/protrans/replica/nightly_1119_work/src
r=0
ONLY=$(python3 -c "import json;print(','.join(json.load(open('$W/ids_$T.json'))))") PICKER_WIN=$W/win_${T}_r1.json WORKERS=3 python3 replica/eval_gate.py "sp1119${T}1={}" || r=$((r+1))
python3 replica/hc2_arrays.py sp1119${T}1 || r=$((r+1))
python3 - <<PY
import pickle, json, sys
sys.path.insert(0, 'replica'); import final_eval as FE
A = pickle.load(open('replica/hc2_cache/arr_sp1119${T}1.pkl', 'rb'))
fail = [k for k, a in A.items() if FE.flags(a)['HC_A'] or FE.flags(a)['HC_B']]
json.dump(fail, open('$W/ids_${T}_r2.json', 'w')); print('rank1 fails', len(fail), 'of', len(A))
PY
if [ -s $W/ids_${T}_r2.json ] && [ "$(cat $W/ids_${T}_r2.json)" != "[]" ]; then
  ONLY=$(python3 -c "import json;print(','.join(json.load(open('$W/ids_${T}_r2.json'))))") PICKER_WIN=$W/win_${T}_r2.json WORKERS=3 python3 replica/eval_gate.py "sp1119${T}2={}" || r=$((r+1))
  python3 replica/hc2_arrays.py sp1119${T}2 || r=$((r+1))
fi
echo "RENDERS_DONE rc=$r"; exit $r
