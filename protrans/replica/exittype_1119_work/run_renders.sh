#!/bin/bash
# 2026-11-19 exit-type picker: render changed dev windows (PICKER_WIN) for hard checks, then cache v2 arrays. Never touches holdout/fresh.
cd /workspace/mixes/protrans || exit 1
W=/workspace/mixes/protrans/replica/exittype_1119_work
export EXTRA_SRC=/workspace/mixes/protrans/replica/nightly_1119_work/src
r=0
for v in et1119c et1119k; do
  ONLY=$(python3 -c "import json;print(','.join(json.load(open('$W/ids_$v.json'))))") PICKER_WIN=$W/win_$v.json WORKERS=3 python3 replica/eval_gate.py "$v={}" || r=$((r+1))
  python3 replica/hc2_arrays.py $v || r=$((r+1))
done
echo "RENDERS_DONE rc=$r"; exit $r
