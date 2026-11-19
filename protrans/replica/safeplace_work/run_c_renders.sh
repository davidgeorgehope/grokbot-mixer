#!/bin/bash
# rerun only the c renders (plan_c already written) + the comparison
cd /workspace/mixes/protrans/replica || exit 1
bash safeplace_work/run_renders.sh c || exit 4
python3 safeplace_eval.py c || exit 5
