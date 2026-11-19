#!/bin/bash
# 2026-11-19 variant e = d + RISKVETO (pre-render veto / replan from the fold's own risk model, tau = 80th pct of its training risk). Dev LODO.
cd /workspace/mixes/protrans/replica || exit 1
export PUMPF=1 LANES=1 TAIL6=1 GAPX=1 SECPEN=0.1 PAYPEN=0.3 RISKVETO=1 EXTRA_RV=sp1119a1,sp1119a2,sp1119b1,sp1119b2
python3 safeplace_1119.py plan e 0.1 || exit 3
bash safeplace_work/run_renders.sh e || exit 4
python3 safeplace_eval.py e || exit 5
python3 safeplace_cmp_1119.py e d || exit 6
