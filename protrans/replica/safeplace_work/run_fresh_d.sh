#!/bin/bash
# 2026-11-19 PLACE=safe variant d fresh validation (isolated fresh_work_t, DJ not in dev): default render -> plan (frozen d) -> rank-1 -> rank-2 for fails -> eval
export FRESH_DIR=fresh_work_t FRESH_NIGHT=2026-11-19-day-safeplace-c FTAG=G FDEF=fdef1119t PUMPF=1 LANES=1 TAIL6=1 GAPX=1 SECPEN=0.1 PAYPEN=0.3 EXTRA_RV=sp1119a1,sp1119a2,sp1119b1,sp1119b2
cd /workspace/mixes/protrans || exit 1
W=/workspace/mixes/protrans/replica/safeplace_work; FW=/workspace/mixes/protrans/replica/fresh_work_t
export GATE_FEAT=$FW/features GATE_FLIB=$FW/lib EXTRA_SRC=$FW/lib
MIX=$(python3 -c "import json;print([m for m in json.load(open('replica/fresh_mixes.json'))['mixes'] if m.get('for_night')=='2026-11-19-day-safeplace-c'][-1]['mix_id'])")
echo "fresh mix $MIX"
ONLY=$MIX WORKERS=3 python3 replica/eval_gate.py "fdef1119t={}" || exit 2
python3 replica/hc2_arrays.py fdef1119t || exit 3
python3 replica/safeplace_fresh_1119s.py plan || exit 4
ONLY=$(python3 -c "import json;print(','.join(json.load(open('$W/ids_G.json'))))") PICKER_WIN=$W/win_G_r1.json WORKERS=3 python3 replica/eval_gate.py "sp1119G1={}" || exit 5
python3 replica/hc2_arrays.py sp1119G1 || exit 6
python3 - <<PY
import pickle, json, sys
sys.path.insert(0, 'replica'); import final_eval as FE
A = pickle.load(open('replica/hc2_cache/arr_sp1119G1.pkl', 'rb'))
fail = [k for k, a in A.items() if FE.flags(a)['HC_A'] or FE.flags(a)['HC_B']]
json.dump(fail, open('$W/ids_G_r2.json', 'w')); print('rank1 fails', len(fail), 'of', len(A))
PY
if [ "$(cat $W/ids_G_r2.json)" != "[]" ]; then
  ONLY=$(python3 -c "import json;print(','.join(json.load(open('$W/ids_G_r2.json'))))") PICKER_WIN=$W/win_G_r2.json WORKERS=3 python3 replica/eval_gate.py "sp1119G2={}" || exit 7
  python3 replica/hc2_arrays.py sp1119G2 || exit 8
fi
python3 replica/safeplace_fresh_1119s.py eval
