#!/bin/bash
cd /workspace/mixes/viz06v3
while pgrep -f "\./run.sh" >/dev/null; do sleep 60; done
for k in 1 2 3; do
  n=$(ls seg??.mp4 2>/dev/null | wc -l); [ "$n" -ge 18 ] && grep -q "VIZDONE 0" run.log && break
  ./run1.sh > run.log 2>&1
done
./after.sh > after.log 2>&1; touch SUPER_DONE
