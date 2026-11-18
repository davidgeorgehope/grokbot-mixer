#!/usr/bin/env bash
# DROP_SWAP (2026-11-18) like-for-like cohort: current rules.json vs rules + DROP_SWAP=1, then blend diagnostics.
set -euo pipefail
cd /workspace/mixes
python3 - <<'PY'
import json;r=json.load(open('protrans/rules.json'));r['DROP_SWAP']=1
json.dump(r,open('/tmp/rules_dropswap_1118.json','w'),indent=1)
PY
python3 protrans/eval_cohort.py d1118_base
python3 protrans/eval_cohort.py ds1118_dropswap /tmp/rules_dropswap_1118.json
python3 protrans/eval_tailexit.py d1118_base ds1118_dropswap
