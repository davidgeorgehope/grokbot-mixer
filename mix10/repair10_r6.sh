#!/usr/bin/env bash
# Repair Mix 10 r5: replace Hayling (exposed mid-track breakdown = E1 at 14:24) and
# rewindow/replace Strings Of Life -> Just Hold On (entry cliff = N1 at 18:45).
# Uses the same crate/table/env as r5. Does not loosen any threshold.
set -euo pipefail
cd /workspace/mixes/src2
_CRATE=/workspace/mixes/mix10/crate_r5.txt
_TABLE=pair_table_10r5.json
. ../mix10/env10.sh
export CRATE_FILE="$_CRATE" PAIR_TABLE="$_TABLE"
exec python3 repair.py --plan plan_mix10_r5.json --out plan_mix10_r6.json --render mix10_r5 \
  --culprit '7Itbo72XEz4>3cOEsXf-ic0:E1,AC3eEHeLd8A>cxS6yd0UAxw:N1'
