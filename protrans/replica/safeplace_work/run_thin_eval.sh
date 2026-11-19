#!/bin/bash
# 2026-11-19 RCA thin flags: (1) dev renders of the pairs whose engine windows change (base re-rendered on the same pairs for like-for-like),
# (2) protrans cohort held-out/train scores for each flag (rules.json copies; floor cb1119_base 34.07 / 32.40 from 01:18 today).
cd /workspace/mixes/protrans || exit 1
unset GATE_FEAT GATE_FLIB PICKER_WIN ONLY BAR_RESYNC THINDEF
export EXTRA_SRC=/workspace/mixes/protrans/replica/nightly_1119_work/src
DEVIDS=$(python3 -c "
import json,sys;sys.path.insert(0,'replica');import safeplace_1119 as S
dev={r['id'] for r in S.dev_rows()};ch=json.load(open('replica/thin_changed_1119.json'))
print(','.join(sorted({i for v in ch.values() for i in v if i in dev})))" 2>/dev/null)
echo "dev changed ids: $(echo $DEVIDS | tr ',' '\n' | wc -l)"
r=0
ONLY=$DEVIDS WORKERS=4 python3 replica/eval_gate.py 'thbase1119={}' 'thinA1119={"STRUCT_THIN":1}' 'thinB1119={"THIN_DROPCUE":1}' 'thinAB1119={"STRUCT_THIN":1,"THIN_DROPCUE":1}' || r=$((r+1))
for v in thbase1119 thinA1119 thinB1119 thinAB1119; do python3 replica/hc2_arrays.py $v || r=$((r+1)); done
echo "DEV_DONE rc=$r"
cd /workspace/mixes
python3 - <<'PY'
import json;r=json.load(open('protrans/rules.json'))
assert not r.get('STRUCT_THIN') and not r.get('THIN_DROPCUE')
for n,f in (('A',{'STRUCT_THIN':1}),('B',{'THIN_DROPCUE':1}),('AB',{'STRUCT_THIN':1,'THIN_DROPCUE':1})):
    q=dict(r);q.update(f);json.dump(q,open(f'/tmp/rules_thin_1119_{n}.json','w'),indent=1)
PY
python3 protrans/eval_cohort.py thinA_1119 /tmp/rules_thin_1119_A.json || r=$((r+1))
python3 protrans/eval_cohort.py thinB_1119 /tmp/rules_thin_1119_B.json || r=$((r+1))
python3 protrans/eval_cohort.py thnAB_1119 /tmp/rules_thin_1119_AB.json || r=$((r+1))
echo "ALL_DONE rc=$r"; exit $r
