#!/bin/bash
# 2026-11-19 day variant c: b + real fader/EQ lane sim features (LANES), pro-p95 gap constraint (GAPX), strict tail (TAIL6). Dev LODO.
cd /workspace/mixes/protrans/replica || exit 1
export PUMPF=1 LANES=1 TAIL6=1 GAPX=1 SECPEN=0.1 EXTRA_RV=sp1119a1,sp1119a2,sp1119b1,sp1119b2
TAG=_c python3 safeplace_1119.py risk || exit 2
python3 safeplace_1119.py plan c 0.1 || exit 3
bash safeplace_work/run_renders.sh c || exit 4
python3 safeplace_eval.py c || exit 5
