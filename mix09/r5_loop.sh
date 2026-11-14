#!/usr/bin/env bash
# Mix 09 r5: r4 (repair round 0) failed only P1 (true peak -0.7 dBTP at gain 9.3; MP3 overshoot over the unchanged limiter) and a
# 2-bar bassgap at trans 1 (hNV8hn33JUU>I9QGpHScGug, mix bar 357). Master chain unchanged; gain 8.0 (measured on r3 raw:
# 8.8 -> -0.7 dBTP, 8.3 -> -1.0). Repair the bassgap pair (rewindow / swap, tests untouched), render up to 2 rounds.
set -uo pipefail
cd /workspace/mixes/src2; . ../mix09/env09.sh
which rubberband rsync >/dev/null || { echo "missing rubberband/rsync"; exit 1; }
python3 -u repair.py --plan plan_mix09_r4.json --out plan_mix09_r5.json --culprit 'hNV8hn33JUU>I9QGpHScGug:bassgap' \
  --history mix09_r3 --table pair_table_09r3.json --crate ../mix09/crate.txt --tag mix09r5_ --budget-s 2400 --max-dry 200 \
  --rounds 2 --render-name mix09_r5 --gain 8.0 --nudge nudge08_r9c.json --render-script ../mix09/render09.sh
