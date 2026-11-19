#!/bin/bash
# 2026-11-19 EXITPOS_DROP shadow eval (epgdrop-1119).
# Allow an exit at the end of the last drop (epg2 behaviour) only when drop 1
# lands in the blend, there is no hard fail, and the outgoing outro is quieter
# or thinner than the drop; block when pro data shows the outro carried the blend.
# One arm only. Does not write rules.json. Does not displace epg_strict.
set -e
cd /workspace/mixes/protrans/replica || exit 1
unset GATE_FEAT GATE_FLIB PICKER_WIN ONLY BAR_RESYNC THINDEF
export TD_TAG=epgdrop TD_POOL=6 TD_CFG='{"base":{},"DROP":{"EXITPOS":"1","EXITPOS_DROP":"1"}}'
rm -f epgdrop_detect_1119.json epgdrop_changed_1119.json
python3 thin_detect_1119.py || exit 2
cd /workspace/mixes/protrans
export EXTRA_SRC=/workspace/mixes/protrans/replica/nightly_1119_work/src
unset TD_TAG TD_POOL TD_CFG
DROPI=$(python3 -c "import json;ch=json.load(open('replica/epgdrop_changed_1119.json'));print(','.join(ch['DROP']) or 'none')")
r=0
ONLY=$DROPI WORKERS=5 python3 replica/eval_gate.py 'epgdrop_1119={"EXITPOS":1,"EXITPOS_DROP":1}' || r=$((r+1))
python3 replica/hc2_arrays.py epgdrop_1119 || r=$((r+1))
echo "DEV_DONE rc=$r"
cd /workspace/mixes
python3 protrans/replica/safeplace_work/write_tmp_rules_epgdrop.py
python3 protrans/replica/seed_cohort_1119.py protrans/replica/epgdrop_detect_1119.json DROP cs_epgdrop_1119
python3 protrans/replica/safeplace_work/seed_epgdrop_from_epg2.py
python3 protrans/eval_cohort.py cs_epgdrop_1119 /tmp/rules_epgdrop_1119.json || r=$((r+1))
cd protrans/replica
python3 arm_eval_report_1119.py epgdrop_eval_1119.json epgdrop_changed_1119.json epbasem DROP:epgdrop_1119:cs_epgdrop_1119 || r=$((r+1))
echo "ALL_DONE rc=$r"; exit $r
