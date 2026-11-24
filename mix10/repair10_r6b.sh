#!/usr/bin/env bash
# Mix 10 r6b: fair per-pair repair budget, entry_cliff rewindows to a longer blend /
# earlier cue / looped intro (check unchanged). Same crate/table/env as r5.
set -euo pipefail
export PYTHONUNBUFFERED=1
cd /workspace/mixes/src2
_CRATE=/workspace/mixes/mix10/crate_r5.txt
_TABLE=pair_table_10r5.json
. ../mix10/env10.sh
export CRATE_FILE="$_CRATE" PAIR_TABLE="$_TABLE"
exec python3 repair.py --plan plan_mix10_r5.json --out plan_mix10_r6.json --render mix10_r5 \
  --culprit '7Itbo72XEz4>3cOEsXf-ic0:E1,AC3eEHeLd8A>cxS6yd0UAxw:N1' \
  --budget-s 1800 --max-dry 150
