#!/usr/bin/env bash
# Drive-first archive of Mix 09 round renders, verify, then delete locally.
set -euo pipefail
cd /workspace/mixes/src2; R=~/bin/rclone; D="gdrive:DJ Mixes Archive/mix09"
F="mix09_r3.mp3 mix09_r4.mp3 mix09_r5.mp3 mix09_r5b.mp3"
for f in $F; do $R copyto "$f" "$D/$f"; done
for f in $F; do
  ls=$(stat -c%s "$f"); rs=$($R lsjson "$D/$f" | python3 -c "import json,sys;print(json.load(sys.stdin)[0]['Size'])")
  lm=$(md5sum "$f" | cut -d' ' -f1); rm_=$($R md5sum "$D/$f" | cut -d' ' -f1)
  echo "$f local=$ls remote=$rs md5 $lm $rm_"; [ "$ls" = "$rs" ] && [ "$lm" = "$rm_" ] || { echo "VERIFY FAIL $f"; exit 1; }
done
rm -f $F _dbg09_*.json plan_mix09_r2.pool.json plan_mix09_r3.pool.json plan_mix09_r1.pool.json st/*.json.prefix_bak
echo archived+removed
