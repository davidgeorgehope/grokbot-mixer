#!/usr/bin/env bash
# fresh-mix test renders (mixes listed in replica/fresh_mixes.json; never used for fitting)
cd /workspace/mixes/protrans
M="$(python3 -c "import json;print(','.join(m['mix_id'] for m in json.load(open('replica/fresh_mixes.json'))['mixes']))")"
ONLY="$M" WORKERS=3 python3 replica/eval_gate.py 'fresh_default={}' && \
ONLY="$M" WORKERS=3 python3 replica/eval_gate.py 'fresh_gated={"REPLICA":"gated"}' 'fresh_on={"REPLICA":1}'
