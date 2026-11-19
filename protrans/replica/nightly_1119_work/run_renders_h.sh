#!/bin/bash
# 2026-11-19 wrap-up: render the frozen picker_1119b picks on the locked holdout (11 non-abstained pairs) for hard checks only
cd /workspace/mixes/protrans || exit 1
W=/workspace/mixes/protrans/replica/nightly_1119_work
export EXTRA_SRC=$W/src
ONLY=$(python3 -c "import json;print(','.join(json.load(open('$W/picker_ids_h.json'))))") PICKER_WIN=$W/picker_win_h.json WORKERS=2 python3 replica/eval_gate.py 'hpck1119={}'
