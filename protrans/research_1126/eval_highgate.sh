#!/usr/bin/env bash
# HIGH_GATE (2026-11-26 midnight research): like-for-like 33-pair cohort, fresh base vs HIGH_GATE=1 at two declared
# HIGH_OFS (8 = rules.json; -4 = prefer highs 4 bars BEFORE the bass swap: corpus_v2 pros median -1 bar, SetFlow guide). Pick on TRAIN only. rules.json never written.
set -euo pipefail
cd /workspace/mixes
# single render slot: wait for the nightly's running render job(s) to finish
while grep -l '^running' jobs/fit-pro-fade-*.status jobs/render-*.status 2>/dev/null | grep -q .; do echo "waiting for render slot $(date +%T)"; sleep 60; done
python3 - <<'PY'
import json;r=json.load(open('protrans/rules.json'))
assert not r.get('HIGH_GATE'), 'rules.json must not enable HIGH_GATE'
for o in (8,-4):
    q=dict(r);q.update(HIGH_GATE=1,HIGH_OFS=o)
    json.dump(q,open(f'/tmp/rules_highgate_1126_{o}.json','w'),indent=1)
PY
python3 protrans/eval_cohort.py hgb1126_base
python3 protrans/eval_tailexit.py hgb1126_base
python3 protrans/eval_cohort.py hg8_1126 /tmp/rules_highgate_1126_8.json
python3 protrans/eval_tailexit.py hg8_1126
python3 protrans/eval_cohort.py hgm4_1126 /tmp/rules_highgate_1126_-4.json
python3 protrans/eval_tailexit.py hgm4_1126
python3 protrans/research_1126/eval_v2.py hgb1126_base hg8_1126 hgm4_1126
echo ALLDONE
