#!/bin/bash
# 2026-11-19 EXITPOS_GATE: outro default, earlier exit only when last drop has played, incoming drop1
# is in the blend, and the leave-one-DJ-out gate (or a weird-outro override) says to move.
# rules.json is not written. Arms: EPG = EXITPOS+GATE, EPGS = EXITPOS+GATE+SLOWDOWN.
set -e
cd /workspace/mixes/protrans/replica || exit 1
unset GATE_FEAT GATE_FLIB PICKER_WIN ONLY BAR_RESYNC THINDEF
export TD_TAG=epg TD_POOL=6 TD_CFG='{"base":{},"EPG":{"EXITPOS":"1","EXITPOS_GATE":"1"},"EPGS":{"EXITPOS":"1","EXITPOS_GATE":"1","SLOWDOWN":"1"}}'
rm -f epg_detect_1119.json
python3 thin_detect_1119.py || exit 2
cd /workspace/mixes/protrans
export EXTRA_SRC=/workspace/mixes/protrans/replica/nightly_1119_work/src
unset TD_TAG TD_POOL TD_CFG
read EPGI EPGSI < <(python3 -c "
import json;ch=json.load(open('replica/epg_changed_1119.json'));print(','.join(ch['EPG']) or 'none', ','.join(ch['EPGS']) or 'none')")
r=0
ONLY=$EPGI WORKERS=5 python3 replica/eval_gate.py 'epg_1119={"EXITPOS":1,"EXITPOS_GATE":1}' || r=$((r+1))
ONLY=$EPGSI WORKERS=5 python3 replica/eval_gate.py 'epgs_1119={"EXITPOS":1,"EXITPOS_GATE":1,"SLOWDOWN":1}' || r=$((r+1))
for v in epg_1119 epgs_1119; do python3 replica/hc2_arrays.py $v || r=$((r+1)); done
echo "DEV_DONE rc=$r"
cd /workspace/mixes
python3 - <<'PY'
import json
r=json.load(open('protrans/rules.json')); assert not r.get('EXITPOS') and not r.get('EXITPOS_GATE')
for n,f in (('epg',{'EXITPOS':1,'EXITPOS_GATE':1}),('epgs',{'EXITPOS':1,'EXITPOS_GATE':1,'SLOWDOWN':1})):
    q=dict(r);q.update(f);json.dump(q,open(f'/tmp/rules_epg_1119_{n}.json','w'),indent=1)
PY
python3 protrans/replica/seed_cohort_1119.py protrans/replica/epg_detect_1119.json EPG cs_epg_1119
python3 protrans/replica/seed_cohort_1119.py protrans/replica/epg_detect_1119.json EPGS cs_epgs_1119
python3 protrans/eval_cohort.py cs_epg_1119 /tmp/rules_epg_1119_epg.json || r=$((r+1))
python3 protrans/eval_cohort.py cs_epgs_1119 /tmp/rules_epg_1119_epgs.json || r=$((r+1))
cd protrans/replica
python3 arm_eval_report_1119.py epg_eval_1119.json epg_changed_1119.json epbasem EPG:epg_1119:cs_epg_1119 EPGS:epgs_1119:cs_epgs_1119 || r=$((r+1))
echo "ALL_DONE rc=$r"; exit $r
