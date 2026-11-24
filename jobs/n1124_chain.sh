#!/usr/bin/env bash
# wait (event-driven, 60 s cheap check) until the other agent's estab-cohort-1124 eval is finished, then run the nightly
cd /workspace/mixes
while grep -q '^running' jobs/estab-cohort-1124.status 2>/dev/null; do sleep 60; done
echo "estab finished: $(cat jobs/estab-cohort-1124.status)"
exec bash jobs/runjob.sh nightly-n1124 python3 protrans/nightly_1124_wrap.py
