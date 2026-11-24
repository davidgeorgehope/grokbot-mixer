#!/usr/bin/env bash
# Mix 10 r6c: dry no-Memory-Lane plans from the r6 pool (avoids the src 128-155
# hole), then render the first ALL OK plan at gain 9.0. Does not loosen checks.
set -euo pipefail
export PYTHONUNBUFFERED=1
cd /workspace/mixes/src2
_CRATE=${CRATE_FILE:-/workspace/mixes/mix10/crate_r5.txt}
_TABLE=${PAIR_TABLE:-pair_table_10r6.json}
. /workspace/mixes/mix10/env10.sh
export CRATE_FILE="$_CRATE" PAIR_TABLE="$_TABLE"

python3 - <<'PY'
import json,sys,os
import plan_search as PS

POOL='plan_mix10_r6.pool.json'
OUT='plan_mix10_r6c.json'
# Prefer more drop_end margin, then coverage / bob16, still inside 60-68 min.
# These have no Memory Lane, no forbidden ids, no entry_cliff (pre-checked).
CANDS=(28872, 5795, 5806, 6436, 4690, 1521)
pool=json.load(open(POOL))
for idx in CANDS:
    d=pool[idx]
    P=PS.to_plan(d,'plan_mix10_base.json')
    print(f'--- dry pool[{idx}] n={len(d["seq"])} pred_len={d["pred"]["len_min"]} drop_end={d["pred"]["drop_end"]} ---', flush=True)
    r=PS.dry(P,f'r6c_{idx}')
    tests=r.get('tests') or {}
    print(json.dumps({k:r.get(k) for k in ('all_ok','len_min','tests','warn','error','cov_min','cov_mean','bob16','entry_cliffs')},indent=1,default=str), flush=True)
    if r.get('all_ok'):
        json.dump(P,open(OUT,'w'),indent=1)
        json.dump(dict(pool_index=idx,pred=d['pred'],seq=d['seq']),open('plan_mix10_r6c.origin.json','w'),indent=1)
        print('DRY ALL OK wrote',OUT,'from pool',idx, flush=True)
        sys.exit(0)
    fails=sorted(k for k,v in tests.items() if not v)
    print('DRY FAILED',fails,'pool',idx, flush=True)
print('no candidate dried ALL OK', flush=True)
sys.exit(2)
PY

exec bash /workspace/mixes/mix10/render10.sh plan_mix10_r6c.json mix10_r6 mix10_r6.mp3 9.0
