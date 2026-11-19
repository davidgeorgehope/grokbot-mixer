#!/bin/bash
# 2026-11-19 EXITPOS v2 (payoff guard fixed: A plays its last drop to its end / to its latest allowed exit; blend overlaps at most its
# last 32 bars; latest allowed exit counts as "plays to the end"). (1) which pairs' family windows change vs base; (2) dev + cohort
# renders only there (others identical to the base render by construction; base = epbasem); (3) cohort held-out (unchanged pairs
# seeded from cb1119_base); (4) report.
cd /workspace/mixes/protrans/replica || exit 1
unset GATE_FEAT GATE_FLIB PICKER_WIN ONLY BAR_RESYNC THINDEF
export TD_TAG=ep2 TD_POOL=6 TD_CFG='{"base":{},"EP":{"EXITPOS":"1"},"EPS":{"EXITPOS":"1","SLOWDOWN":"1"}}'
rm -f ep2_detect_1119.json
python3 thin_detect_1119.py || exit 2
cd /workspace/mixes/protrans
export EXTRA_SRC=/workspace/mixes/protrans/replica/nightly_1119_work/src
unset TD_TAG TD_POOL TD_CFG
read EPI EPSI < <(python3 -c "
import json;ch=json.load(open('replica/ep2_changed_1119.json'));print(','.join(ch['EP']) or 'none', ','.join(ch['EPS']) or 'none')")
r=0
ONLY=$EPI WORKERS=5 python3 replica/eval_gate.py 'ep2_1119={"EXITPOS":1}' || r=$((r+1))
ONLY=$EPSI WORKERS=5 python3 replica/eval_gate.py 'ep2s_1119={"EXITPOS":1,"SLOWDOWN":1}' || r=$((r+1))
for v in ep2_1119 ep2s_1119; do python3 replica/hc2_arrays.py $v || r=$((r+1)); done
echo "DEV_DONE rc=$r"
cd /workspace/mixes
python3 - <<'PY'
import json;r=json.load(open('protrans/rules.json')); assert not r.get('EXITPOS')
for n,f in (('ep',{'EXITPOS':1}),('eps',{'EXITPOS':1,'SLOWDOWN':1})):
    q=dict(r);q.update(f);json.dump(q,open(f'/tmp/rules_ep2_1119_{n}.json','w'),indent=1)
PY
python3 protrans/replica/seed_cohort_1119.py protrans/replica/ep2_detect_1119.json EP cs_ep2_1119
python3 protrans/replica/seed_cohort_1119.py protrans/replica/ep2_detect_1119.json EPS cs_ep2s_1119
for n in ep2 ep2s; do f=$([ $n = ep2 ] && echo ep || echo eps); python3 protrans/eval_cohort.py cs_${n}_1119 /tmp/rules_ep2_1119_${f}.json || r=$((r+1)); done
cd protrans/replica
python3 arm_eval_report_1119.py ep2_eval_1119.json ep2_changed_1119.json epbasem EP:ep2_1119:cs_ep2_1119 EPS:ep2s_1119:cs_ep2s_1119 || r=$((r+1))
echo "ALL_DONE rc=$r"; exit $r
