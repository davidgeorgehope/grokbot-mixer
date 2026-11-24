#!/usr/bin/env bash
# wait for prep-mix10 + restore-mix10, then run search-mix10-r1 through runjob.sh
J=/workspace/mixes/jobs
for j in prep-mix10 restore-mix10; do
  while grep -q '^running' $J/$j.status 2>/dev/null; do sleep 20; done
  grep -q '^done' $J/$j.status || { echo "$j not done: $(cat $J/$j.status)"; exit 1; }
done
exec $J/runjob.sh search-mix10-r1 bash /workspace/mixes/mix10/search10.sh plan_mix10_r1.json
