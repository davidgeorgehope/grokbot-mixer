#!/usr/bin/env bash
# LEVEL_COMP (2026-11-27 midnight research): like-for-like 33-pair cohort, fresh default (ridegate) vs LEVEL_COMP=1. rules.json never written.
set -euo pipefail
cd /workspace/mixes
python3 - <<'PY'
import json;r=json.load(open('protrans/rules.json'))
assert not r.get('LEVEL_COMP')
q=dict(r);q.update(LEVEL_COMP=1);json.dump(q,open('/tmp/rules_levelcomp_1127.json','w'),indent=1)
PY
python3 protrans/eval_cohort.py lc_1127 /tmp/rules_levelcomp_1127.json
python3 protrans/eval_tailexit.py lc_1127
python3 protrans/eval_cohort.py lcb_1127
python3 protrans/eval_tailexit.py lcb_1127
python3 protrans/research_1126/eval_v2.py lcb_1127 lc_1127
echo ALLDONE
