#!/usr/bin/env bash
# n1126 renders (single render slot): wait (cheap 60 s check) until the other agent's highgate-cohort-1126 eval is done and the
# n1126 protrans maps exist, then: default base (33 pairs) + official hard checks + injected-fault detector rates, then the two frozen arms.
cd /workspace/mixes
while grep -q '^running' jobs/highgate-cohort-1126.status 2>/dev/null; do sleep 60; done
echo "render slot free: highgate $(cat jobs/highgate-cohort-1126.status) at $(date)"
while [ ! -f protrans/replica/nightly_1126_work/map_ridegate_tail.json ]; do sleep 60; done
set -e
R=protrans/replica
nice -n 10 python3 $R/render_1126.py base n26b
nice -n 10 python3 $R/hc_1126.py n1126_base
nice -n 10 python3 $R/render_1126.py ridegate n26r
nice -n 10 python3 $R/hc_1126.py n1126_ridegate
nice -n 10 python3 $R/render_1126.py ridegate_tail n26t
nice -n 10 python3 $R/hc_1126.py n1126_ridegate_tail
nice -n 10 python3 $R/hcinject_1126.py n1126_base
echo ALLDONE $(date)
