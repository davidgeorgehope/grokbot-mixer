#!/usr/bin/env bash
# CONSONANCE (2026-11-19) like-for-like cohort: current rules.json vs rules + CONSONANCE=1 at two pre-declared weights
# (0.3 and 1.0; variant names need distinct 6-char prefixes because render tags are variant[:6]; the weight is chosen on TRAIN mean only), then blend diagnostics (must-pass, dip, spectral clash).
set -euo pipefail
cd /workspace/mixes
python3 - <<'PY'
import json;r=json.load(open('protrans/rules.json'))
assert not r.get('CONSONANCE'), 'rules.json must not enable CONSONANCE'
for w in ('0.3','1.0'):
    q=dict(r);q['CONSONANCE']=1;q['CONSONANCE_W']=float(w)
    json.dump(q,open(f'/tmp/rules_cons_1119_w{w.replace(".","")}.json','w'),indent=1)
PY
python3 protrans/eval_cohort.py cb1119_base
python3 protrans/eval_cohort.py cw03_1119 /tmp/rules_cons_1119_w03.json
python3 protrans/eval_cohort.py cw10_1119 /tmp/rules_cons_1119_w10.json
python3 protrans/eval_tailexit.py cb1119_base cw03_1119 cw10_1119
