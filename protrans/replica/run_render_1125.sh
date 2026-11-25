#!/usr/bin/env bash
# n1125 renders: wait (cheap 60 s check) until the other agent's midhold-cohort-1125 eval is done, then render the frozen arms.
cd /workspace/mixes
while grep -q '^running' jobs/midhold-cohort-1125.status 2>/dev/null; do sleep 60; done
echo "midhold finished: $(cat jobs/midhold-cohort-1125.status) at $(date)"
set -e
nice -n 10 python3 protrans/replica/render_1125.py ridegate n25rg
nice -n 10 python3 protrans/replica/hc_1125.py n1125_ridegate
nice -n 10 python3 protrans/replica/render_1125.py cueonly_gated n25cq
nice -n 10 python3 protrans/replica/hc_1125.py n1125_cueonly_gated
echo ALLDONE $(date)
