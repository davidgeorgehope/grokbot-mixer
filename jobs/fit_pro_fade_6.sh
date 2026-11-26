#!/usr/bin/env bash
# fit-pro-fade-6: wait for the single render slot, then run the r6 early-exit fade grid.
# Nightly render-n1126 has priority (it is already queued behind highgate-cohort-1126).
# Cheap 60 s status wait, same pattern as protrans/replica/run_render_1126.sh.
set -euo pipefail
cd /workspace/mixes
while grep -q '^running' jobs/render-n1126.status 2>/dev/null || grep -q '^running' jobs/highgate-cohort-1126.status 2>/dev/null; do
  echo "waiting for render slot $(date +%T) render-n1126=$(tr -d '\n' < jobs/render-n1126.status) highgate=$(tr -d '\n' < jobs/highgate-cohort-1126.status)"
  sleep 60
done
echo "render slot free at $(date) render-n1126=$(cat jobs/render-n1126.status) highgate=$(cat jobs/highgate-cohort-1126.status)"
export PRO_FADE_RESPECT_EXIT=1
export PFW="${PFW:-4}"
export PYTHONUNBUFFERED=1
cd /workspace/mixes/protrans/replica
exec nice -n 10 python3 nightly_1125_work/profade_fit/r6_grid.py
