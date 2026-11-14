#!/usr/bin/env bash
# Mix 09 r3: render the searched plan; if guardrails/pytest fail, repair.py (swap incoming / rewindow, tests untouched) up to 3 rounds.
set -uo pipefail
cd /workspace/mixes/src2; . ../mix09/env09.sh
which rubberband rsync >/dev/null || { echo "missing rubberband/rsync"; exit 1; }
PLAN=${1:-plan_mix09_r3.json}
bash ../mix09/render09.sh "$PLAN" mix09_r3 mix09_r3.mp3 9.3 nudge08_r9c.json && { echo "R3 PASS"; exit 0; }
echo "R3 render failed -> repair"
python3 -u repair.py --plan "$PLAN" --out plan_mix09_r4.json --render mix09_r3 \
  --table pair_table_09r3.json --crate ../mix09/crate.txt --tag mix09r4_ --budget-s 3000 --max-dry 300 \
  --rounds 3 --render-name mix09_r4 --gain 9.3 --nudge nudge08_r9c.json --render-script ../mix09/render09.sh
