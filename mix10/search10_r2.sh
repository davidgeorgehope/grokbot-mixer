#!/usr/bin/env bash
# Mix 10 round 2: same limits as r1, crate minus pUUrJH7jzAQ and ujjImKRMX-M (no 16-bar beat-on-beat entry)
set -euo pipefail
cd /workspace/mixes/src2
# env10.sh sets CRATE_FILE to crate.txt; override after source
. ../mix10/env10.sh
export CRATE_FILE=/workspace/mixes/mix10/crate_r2.txt
export NPAR=${NPAR:-2}  # be kind to the concurrent Saturday nightly
exec bash ../mix10/search10.sh plan_mix10_r2.json
