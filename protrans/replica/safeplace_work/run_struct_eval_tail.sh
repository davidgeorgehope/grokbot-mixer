cd /workspace/mixes/protrans; r=0
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
