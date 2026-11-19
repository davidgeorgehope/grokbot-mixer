#!/bin/bash
# 2026-11-19 EXITPOS_GATE rerun (epg2): first epg-1119 was a no-op because the gate only
# reordered pair_cands while blend_bench.families() / DUMP_CANDS pick min engine cost,
# so EPG==EP and EPGS==EPS. mix_simple now rewrites costs (and gates nat_short / nat_long
# separately). New tags so the ungated caches are not reused. rules.json is not written.
set -e
cd /workspace/mixes/protrans/replica || exit 1
unset GATE_FEAT GATE_FLIB PICKER_WIN ONLY BAR_RESYNC THINDEF
export TD_TAG=epg2 TD_POOL=6 TD_CFG='{"base":{},"EPG":{"EXITPOS":"1","EXITPOS_GATE":"1"},"EPGS":{"EXITPOS":"1","EXITPOS_GATE":"1","SLOWDOWN":"1"}}'
rm -f epg2_detect_1119.json epg2_changed_1119.json
python3 thin_detect_1119.py || exit 2
cd /workspace/mixes/protrans
export EXTRA_SRC=/workspace/mixes/protrans/replica/nightly_1119_work/src
unset TD_TAG TD_POOL TD_CFG
read EPGI EPGSI < <(python3 -c "
import json;ch=json.load(open('replica/epg2_changed_1119.json'));print(','.join(ch['EPG']) or 'none', ','.join(ch['EPGS']) or 'none')")
r=0
ONLY=$EPGI WORKERS=5 python3 replica/eval_gate.py 'epg2_1119={"EXITPOS":1,"EXITPOS_GATE":1}' || r=$((r+1))
ONLY=$EPGSI WORKERS=5 python3 replica/eval_gate.py 'epgs2_1119={"EXITPOS":1,"EXITPOS_GATE":1,"SLOWDOWN":1}' || r=$((r+1))
for v in epg2_1119 epgs2_1119; do python3 replica/hc2_arrays.py $v || r=$((r+1)); done
echo "DEV_DONE rc=$r"
cd /workspace/mixes
python3 - <<'PY'
import json
r=json.load(open('protrans/rules.json')); assert not r.get('EXITPOS') and not r.get('EXITPOS_GATE') and not r.get('SLOWDOWN')
for n,f in (('epg',{'EXITPOS':1,'EXITPOS_GATE':1}),('epgs',{'EXITPOS':1,'EXITPOS_GATE':1,'SLOWDOWN':1})):
    q=dict(r);q.update(f);json.dump(q,open(f'/tmp/rules_epg2_1119_{n}.json','w'),indent=1)
PY
python3 protrans/replica/seed_cohort_1119.py protrans/replica/epg2_detect_1119.json EPG cs_epg2_1119
python3 protrans/replica/seed_cohort_1119.py protrans/replica/epg2_detect_1119.json EPGS cs_epgs2_1119
python3 protrans/eval_cohort.py cs_epg2_1119 /tmp/rules_epg2_1119_epg.json || r=$((r+1))
python3 protrans/eval_cohort.py cs_epgs2_1119 /tmp/rules_epg2_1119_epgs.json || r=$((r+1))
cd protrans/replica
python3 arm_eval_report_1119.py epg2_eval_1119.json epg2_changed_1119.json epbasem EPG:epg2_1119:cs_epg2_1119 EPGS:epgs2_1119:cs_epgs2_1119 || r=$((r+1))
echo "ALL_DONE rc=$r"; exit $r
