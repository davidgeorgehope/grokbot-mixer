#!/usr/bin/env bash
set -euo pipefail
cd /workspace/mixes/src2
python3 blend_gate_validate.py 2
python3 blend_gate_validate.py 2 holdout
python3 - <<'PY'
import json
m10 = json.load(open('/workspace/mixes/eval/blend_gate_validation_mix10.json'))
ho = json.load(open('/workspace/mixes/eval/blend_gate_validation_holdout.json'))
tot_c = sum(v['caught'] for d in (m10, ho) for v in d['mixes'].values())
tot_k = sum(v['known'] for d in (m10, ho) for v in d['mixes'].values())
tot_ff = sum(v['false_fails'] for d in (m10, ho) for v in d['mixes'].values())
tot_cl = sum(v['clean'] for d in (m10, ho) for v in d['mixes'].values())
print(f'TOTAL caught={tot_c}/{tot_k} false_fails={tot_ff}/{tot_cl} total_blends={tot_k+tot_cl}')
for dname, d in (('mix10', m10), ('holdout', ho)):
    for m, v in d['mixes'].items():
        print(f'  {dname}:{m} caught={v["caught"]}/{v["known"]} false_fails={v["false_fails"]}/{v["clean"]} wall_s={v["wall_s"]}')
PY
