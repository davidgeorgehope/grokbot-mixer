#!/usr/bin/env bash
# Mix 10 r6: dry the Memory Lane→Lilies rewindow (e=240 / ib=64 / 32-bar; the
# search window started in Memory Lane's mid-track breakdown at src 128), then
# render at gain 9.0 only if dry is ALL OK. Tests run inside render10.sh.
# Does not loosen any check.
set -euo pipefail
export PYTHONUNBUFFERED=1
cd /workspace/mixes/src2
_CRATE=${CRATE_FILE:-/workspace/mixes/mix10/crate_r5.txt}
_TABLE=${PAIR_TABLE:-pair_table_10r6.json}
. /workspace/mixes/mix10/env10.sh
export CRATE_FILE="$_CRATE" PAIR_TABLE="$_TABLE"
PLAN=${PLAN:-plan_mix10_r6b.json}

python3 - <<'PY'
import json,sys
import plan_search as PS
plan=json.load(open("plan_mix10_r6b.json"))
r=PS.dry(plan,"r6b")
keys=('all_ok','len_min','tests','warn','error','cov_min','cov_mean','bob16','entry_cliffs')
print(json.dumps({k:r.get(k) for k in keys},indent=1,default=str), flush=True)
if not r.get('all_ok'):
    print('DRY FAILED', flush=True)
    sys.exit(2)
print('DRY ALL OK', flush=True)
PY

exec bash /workspace/mixes/mix10/render10.sh "$PLAN" mix10_r6 mix10_r6.mp3 9.0
