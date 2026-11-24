#!/usr/bin/env bash
# ESTAB (2026-11-24 midnight research) like-for-like cohort: fresh base on tonight's code vs ESTAB=1 at two weights
# declared in advance (10 and 30 per dB above an 11 dB line = pro median predicted dip on 108 corpus_v2 pairs,
# protrans/research_1124/estab_diag.json). The weight is chosen on TRAIN mean only. Diagnostics run right after each
# variant so the /tmp renders are still there. rules.json is never written.
set -euo pipefail
cd /workspace/mixes
python3 - <<'PY'
import json;r=json.load(open('protrans/rules.json'))
assert not r.get('ESTAB'), 'rules.json must not enable ESTAB'
for w in (10,30):
    q=dict(r);q.update(ESTAB=1,ESTAB_W=w,ESTAB_DB=11)
    json.dump(q,open(f'/tmp/rules_estab_1124_w{w}.json','w'),indent=1)
PY
python3 protrans/eval_cohort.py eb1124_base
python3 protrans/eval_tailexit.py eb1124_base
python3 protrans/eval_cohort.py e10_1124 /tmp/rules_estab_1124_w10.json
python3 protrans/eval_tailexit.py e10_1124
python3 protrans/eval_cohort.py e30_1124 /tmp/rules_estab_1124_w30.json
python3 protrans/eval_tailexit.py e30_1124
echo ALLDONE
