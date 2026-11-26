#!/usr/bin/env bash
# ridegate-live-agree: wait for the single render slot (do not disturb fit-pro-fade-6),
# train the live RIDEGATE pack, agree vs the n1126 map (33) and vs CV (dev), then run tests.
# Does not open the locked holdout and does not write rules.json.
set -euo pipefail
cd /workspace/mixes
while grep -q '^running' jobs/fit-pro-fade-6.status 2>/dev/null \
   || grep -q '^running' jobs/render-n1126.status 2>/dev/null \
   || grep -q '^running' jobs/highgate-cohort-1126.status 2>/dev/null; do
  echo "waiting for render slot $(date +%T) fit-pro-fade-6=$(tr -d '\n' < jobs/fit-pro-fade-6.status)"
  sleep 60
done
echo "render slot free at $(date) fit-pro-fade-6=$(tr -d '\n' < jobs/fit-pro-fade-6.status)"
export PYTHONUNBUFFERED=1
cd /workspace/mixes/protrans/replica
nice -n 10 python3 ridegate_live.py agree
cd /workspace/mixes/protrans
nice -n 10 python3 -m pytest -q tests
echo "TESTS done $(date)"
