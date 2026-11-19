#!/bin/bash
# 2026-11-19 day variant d: c + placement-quality term PAYPEN=0.3 (don't leave the outgoing track before its main payoff / don't cue past
# the incoming's first drop). Same risk model as c. Dev LODO.
cd /workspace/mixes/protrans/replica || exit 1
export PUMPF=1 LANES=1 TAIL6=1 GAPX=1 SECPEN=0.1 PAYPEN=0.3 EXTRA_RV=sp1119a1,sp1119a2,sp1119b1,sp1119b2
python3 safeplace_1119.py plan d 0.1 || exit 3
bash safeplace_work/run_renders.sh d || exit 4
python3 safeplace_eval.py d || exit 5
python3 placequal_1119.py b c d || exit 6
python3 safeplace_cmp_1119.py d c || exit 7
