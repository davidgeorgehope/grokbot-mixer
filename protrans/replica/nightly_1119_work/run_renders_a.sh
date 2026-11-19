#!/bin/bash
# 2026-11-19 nightly renders: (1) real engine default for 33 dev pairs whose sources were restored from Drive; (2) picker windows (PICKER_WIN) for 100 pairs
cd /workspace/mixes/protrans || exit 1
W=/workspace/mixes/protrans/replica/nightly_1119_work
export EXTRA_SRC=$W/src
ONLY=$(python3 -c "import json;print(','.join(json.load(open('$W/restorable_ids.json'))))") WORKERS=3 python3 replica/eval_gate.py 'ndef1119={}' &
p1=$!
ONLY=$(python3 -c "import json;print(','.join(json.load(open('$W/picker_ids_a.json'))))") PICKER_WIN=$W/picker_win_a.json WORKERS=3 python3 replica/eval_gate.py 'pick1119={}' &
p2=$!
wait $p1; r1=$?; wait $p2; r2=$?
echo "RENDERS_DONE ndef=$r1 pick=$r2"; exit $((r1+r2))
