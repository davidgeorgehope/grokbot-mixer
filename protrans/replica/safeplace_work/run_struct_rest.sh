#!/bin/bash
# 2026-11-19: remainder of run_struct_eval.sh after its line-14 syntax slip (dev renders had finished): HC arrays, cohort held-out per arm
# (unchanged cohort pairs pre-seeded from cb1119_base by seed_cohort_1119.py), generic arm report.
cd /workspace/mixes/protrans || exit 1
unset GATE_FEAT GATE_FLIB PICKER_WIN ONLY BAR_RESYNC THINDEF
export EXTRA_SRC=/workspace/mixes/protrans/replica/nightly_1119_work/src
r=0
for v in sbase1119 sqc1119 sslow1119 sqcs1119; do python3 replica/hc2_arrays.py $v || r=$((r+1)); done
cd /workspace/mixes
python3 - <<'PY'
import json;r=json.load(open('protrans/rules.json'))
assert not any(r.get(k) for k in ('OUTRO_QC','SLOWDOWN','STRUCTB'))
for n,f in (('qc',{'OUTRO_QC':1}),('slow',{'SLOWDOWN':1}),('qcs',{'OUTRO_QC':1,'SLOWDOWN':1}),('b0',{'STRUCTB':0}),('b100',{'STRUCTB':100})):
    q=dict(r);q.update(f);json.dump(q,open(f'/tmp/rules_struct_1119_{n}.json','w'),indent=1)
PY
for n in qc slow qcs b100 b0; do python3 protrans/eval_cohort.py cs_${n}_1119 /tmp/rules_struct_1119_${n}.json || r=$((r+1)); done
cd protrans/replica
python3 arm_eval_report_1119.py struct_eval_1119.json struct_changed_1119.json sbase1119 QC:sqc1119:cs_qc_1119 SLOW:sslow1119:cs_slow_1119 QCS:sqcs1119:cs_qcs_1119 B0:-:cs_b0_1119 B100:-:cs_b100_1119 || r=$((r+1))
echo "ALL_DONE rc=$r"; exit $r
