#!/bin/bash
# render -> guardrails+tests -> auto-fix (timing nudges) loop until zero failures or MAX iterations
# usage: iterate.sh PLAN NAME OUT_MP3 GAIN NUDGE_JSON [MAX]
P=$1;N=$2;O=$3;GN=$4;NF=$5;MAX=${6:-4};cd /workspace/mixes/src2
for i in $(seq 1 $MAX);do
  echo "=== iteration $i $(date +%H:%M)";NUDGE=$NF bash ../src/render_and_test4.sh $P $N $O $GN > iter_${N}_$i.log 2>&1;rc=$?
  tail -2 iter_${N}_$i.log;grep -E "^FAIL|passed|failed" iter_${N}_$i.log | cut -c1-160
  [ $rc = 0 ] && { echo "ALL GREEN at iteration $i";exit 0; }
  python3 ../src/autofix.py $N $NF 2>&1 | grep -E "^nudge|changed" | tail -40
  python3 ../src/autofix.py --noop 2>/dev/null; grep -q '"check": "F1"\|"check": "N1"' guard_$N/guardrails.json || { echo "non-timing failures remain; stopping for manual fix";exit 1; }
done;exit 1
