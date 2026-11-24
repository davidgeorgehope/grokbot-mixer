#!/usr/bin/env bash
# Mix 10 round 3: crate_r2 (no Saviour / Tear Drops) + rebuilt pair table after vocfix.
# Same test limits as r1. New PAIR_TABLE because table_key ignores st json content.
set -euo pipefail
cd /workspace/mixes/src2
. ../mix10/env10.sh
export CRATE_FILE=/workspace/mixes/mix10/crate_r2.txt
export PAIR_TABLE=pair_table_10r3.json
export NPAR=${NPAR:-2}
exec bash ../mix10/search10.sh plan_mix10_r3.json
