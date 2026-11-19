#!/bin/bash
# 2026-11-19 OUTRO_QC (primary) + STRUCTB 0/100 ablation + SLOWDOWN: (1) eval_gate renders of every dev + cohort pair whose engine family
# windows change under any arm (base re-rendered on the same pairs), HC arrays; (2) cohort held-out per arm via rules.json copies
# (floor cb1119_base 34.07 / 32.40). rules.json and engine defaults untouched.
cd /workspace/mixes/protrans || exit 1
unset GATE_FEAT GATE_FLIB PICKER_WIN ONLY BAR_RESYNC THINDEF
export EXTRA_SRC=/workspace/mixes/protrans/replica/nightly_1119_work/src
IDS=$(python3 -c "
import json;ch=json.load(open('replica/struct_changed_1119.json'))
print(','.join(sorted({i for k,v in ch.items() if k in ('QC','SLOW','QCS') for i in v})))")
echo "changed ids: $(echo $IDS | tr ',' '\n' | wc -l)"
r=0
ONLY=$IDS WORKERS=4 python3 replica/eval_gate.py 'sbase1119={}' 'sqc1119={"OUTRO_QC":1}' 'sslow1119={"SLOWDOWN":1}' 'sqcs1119={"OUTRO_QC":1,"SLOWDOWN":1}' || r=$((r+1))  # STRUCTB comparison arms held-out only
for v in sbase1119 sqc1119 sslow1119 sqcs1119; do python3 replica/hc2_arrays.py $v || r=$((r+1)); done
echo "DEV_DONE rc=$r"
cd /workspace/mixes
python3 - <<'PY'
import json;r=json.load(open('protrans/rules.json'))
assert not any(r.get(k) for k in ('OUTRO_QC','SLOWDOWN','STRUCTB'))
for n,f in (('qc',{'OUTRO_QC':1}),('slow',{'SLOWDOWN':1}),('qcs',{'OUTRO_QC':1,'SLOWDOWN':1}),('b0',{'STRUCTB':0}),('b100',{'STRUCTB':100})):
    q=dict(r);q.update(f);json.dump(q,open(f'/tmp/rules_struct_1119_{n}.json','w'),indent=1)
PY
for n in qc slow qcs b0 b100; do python3 protrans/eval_cohort.py cs_${n}_1119 /tmp/rules_struct_1119_${n}.json || r=$((r+1)); done
echo "ALL_DONE rc=$r"; exit $r
