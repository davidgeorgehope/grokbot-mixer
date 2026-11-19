#!/bin/bash
# 2026-11-19 EXITPOS (alone / + SLOWDOWN). EXITPOS changes the family windows of all 105 pairs. Base = gate_ckpt 'default' (11-18 22:04;
# identical windows and hard flags to today's re-rendered base on all 16 shared pairs) + epbase1119 for the 14 pairs it lacks. EPS rendered
# only where its windows differ from EP (10 pairs); elsewhere identical by construction. Merged variants: epbasem, epsm.
cd /workspace/mixes/protrans || exit 1
unset GATE_FEAT GATE_FLIB PICKER_WIN ONLY BAR_RESYNC THINDEF
export EXTRA_SRC=/workspace/mixes/protrans/replica/nightly_1119_work/src
read ALL MISS EPSI < <(python3 -c "
import json;d=json.load(open('replica/ep_detect_1119.json'));de={json.loads(l)['id'] for l in open('replica/gate_ckpt/default.jsonl')}
print(','.join(sorted(d)), ','.join(sorted(k for k in d if k not in de)), ','.join(sorted(k for k,o in d.items() if o.get('EPS')!=o.get('EP'))))")
r=0
ONLY=$MISS WORKERS=4 python3 replica/eval_gate.py 'epbase1119={}' || r=$((r+1))
ONLY=$EPSI WORKERS=4 python3 replica/eval_gate.py 'eps1119={"EXITPOS":1,"SLOWDOWN":1}' || r=$((r+1))
ONLY=$ALL WORKERS=4 python3 replica/eval_gate.py 'ep1119={"EXITPOS":1}' || r=$((r+1))
for v in default epbase1119 ep1119 eps1119; do python3 replica/hc2_arrays.py $v || r=$((r+1)); done
python3 - <<'PY'
import json, pickle, os
G='replica/gate_ckpt/'; C='replica/hc2_cache/'
def ck(v): return {json.loads(l)['id']: l for l in open(G+v+'.jsonl')} if os.path.exists(G+v+'.jsonl') else {}
def ar(v): return pickle.load(open(C+f'arr_{v}.pkl','rb')) if os.path.exists(C+f'arr_{v}.pkl') else {}
for out, parts in (('epbasem', ['default', 'epbase1119']), ('epsm', ['ep1119', 'eps1119'])):
    m = {}; a = {}
    for v in parts: m.update(ck(v)); a.update(ar(v))
    open(G+out+'.jsonl','w').write(''.join(m.values())); pickle.dump(a, open(C+f'arr_{out}.pkl','wb')); print(out, len(m), len(a))
PY
echo "DEV_DONE rc=$r"
cd /workspace/mixes
python3 - <<'PY'
import json;r=json.load(open('protrans/rules.json')); assert not r.get('EXITPOS')
for n,f in (('ep',{'EXITPOS':1}),('eps',{'EXITPOS':1,'SLOWDOWN':1})):
    q=dict(r);q.update(f);json.dump(q,open(f'/tmp/rules_ep_1119_{n}.json','w'),indent=1)
PY
python3 protrans/replica/seed_cohort_1119.py protrans/replica/ep_detect_1119.json EP cs_ep_1119
python3 protrans/replica/seed_cohort_1119.py protrans/replica/ep_detect_1119.json EPS cs_eps_1119
for n in ep eps; do python3 protrans/eval_cohort.py cs_${n}_1119 /tmp/rules_ep_1119_${n}.json || r=$((r+1)); done
cd protrans/replica
python3 - <<'PY'
import json; d=json.load(open('ep_detect_1119.json')); json.dump({'EP': sorted(d), 'EPS': sorted(d)}, open('ep_changed_all_1119.json','w'))
PY
python3 arm_eval_report_1119.py ep_eval_1119.json ep_changed_all_1119.json epbasem EP:ep1119:cs_ep_1119 EPS:epsm:cs_eps_1119 || r=$((r+1))
echo "ALL_DONE rc=$r"; exit $r
