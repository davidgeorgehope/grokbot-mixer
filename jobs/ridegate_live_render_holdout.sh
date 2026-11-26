#!/usr/bin/env bash
# ridegate-live-render-holdout: wait for the single render slot, render the n1126 pinned
# set with RIDEGATE=1 (live path, map flags off), confirm official v1 + official hard
# checks match the map-based ridegate render, and only then open the locked holdout
# (2nd opening). Does not write rules.json or change defaults. Does not disturb
# fit-pro-fade-6 (waits until that status is no longer running).
set -euo pipefail
cd /workspace/mixes
while grep -q '^running' jobs/fit-pro-fade-6.status 2>/dev/null \
   || grep -q '^running' jobs/render-n1126.status 2>/dev/null \
   || grep -q '^running' jobs/highgate-cohort-1126.status 2>/dev/null; do
  echo "waiting for render slot $(date +%T) fit-pro-fade-6=$(tr -d '\n' < jobs/fit-pro-fade-6.status)"
  sleep 60
done
echo "render slot free at $(date) fit-pro-fade-6=$(tr -d '\n' < jobs/fit-pro-fade-6.status)"
# Do not inherit leftover picker env; render_1126.py also clears these.
unset PICKER_STYLE_GATED PICKER_STYLE_GATED_MAP PICKER_INJECT_CS PICKER_WIN RIDEGATE RIDEGATE_PACK
export PYTHONUNBUFFERED=1
export WORKERS="${WORKERS:-4}"
R=protrans/replica
# Confirm rules.json still has the picker flags off (never written here).
python3 - <<'PY'
import json, sys
sys.path.insert(0, '/workspace/mixes/protrans')
import paths
r = json.load(open(paths.RULES))
assert not r.get('RIDEGATE') and not r.get('PICKER_STYLE_GATED'), r
print('rules.json picker flags off', paths.RULES)
PY
nice -n 10 python3 $R/render_1126.py ridegate_live n26l
nice -n 10 python3 $R/hc_1126.py n1126_ridegate_live
nice -n 10 python3 $R/compare_ridegate_live_1126.py
echo "LIVE RENDER MATCHED MAP at $(date); opening locked holdout (2nd opening)"
nice -n 10 python3 $R/holdout_1126_live.py
echo "ALLDONE $(date)"
