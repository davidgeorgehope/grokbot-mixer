#!/usr/bin/env bash
# MID_HOLD (2026-11-25 midnight research) like-for-like cohort: fresh base on tonight's code vs MID_HOLD=1 at two depths
# declared in advance (6 and 10 dB under the crossfader until the bass swap). Depth chosen on TRAIN mean only.
# Diagnostics (blend_diag + must-pass) right after each variant while /tmp renders exist. rules.json is never written.
set -euo pipefail
cd /workspace/mixes
python3 - <<'PY'
import json;r=json.load(open('protrans/rules.json'))
assert not r.get('MID_HOLD'), 'rules.json must not enable MID_HOLD'
for db in (6,10):
    q=dict(r);q.update(MID_HOLD=1,MID_HOLD_DB=db)
    json.dump(q,open(f'/tmp/rules_midhold_1125_{db}.json','w'),indent=1)
PY
python3 protrans/eval_cohort.py mhb1125_base
python3 protrans/eval_tailexit.py mhb1125_base
python3 protrans/eval_cohort.py mh6_1125 /tmp/rules_midhold_1125_6.json
python3 protrans/eval_tailexit.py mh6_1125
python3 protrans/eval_cohort.py mh10_1125 /tmp/rules_midhold_1125_10.json
python3 protrans/eval_tailexit.py mh10_1125
echo ALLDONE
