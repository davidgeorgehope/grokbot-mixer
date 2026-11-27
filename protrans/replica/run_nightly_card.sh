#!/usr/bin/env bash
# Render and score the nightly *card* for TAG (default: today's nMMDD).
# Always reads replica/nightly_candidates.json via nightly_card.card_for / nXXXX_run.py.
# Do not put arm names in this script. n1127 skipped ridegate_lock_pump_ee and
# profade_ex35 because jobs/render-n1127 ran run_render_1127.sh, which hardcoded
# dclash_land6 and dclash_land7 instead of reading the card.
set -euo pipefail
cd /workspace/mixes
TAG=${1:-$(date +n%m%d)}
export NIGHTLY_TAG=$TAG
# Prefer a per-tag runner if present (n1128_run.py, ...); else the shared hill-climb.
if [ -f "protrans/${TAG}_run.py" ]; then
  exec nice -n 10 python3 "protrans/${TAG}_run.py"
fi
exec nice -n 10 python3 protrans/nightly_hill_climb.py
