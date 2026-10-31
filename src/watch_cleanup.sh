#!/bin/bash
# after each delivery (deliver/NN/READY_FOR_DRIVE) run cleanup_after_build.sh once no render/test is active
cd /workspace/mixes
while :; do
  for d in deliver/*/; do
    [ -f $d/READY_FOR_DRIVE ] && [ ! -f $d/.cleaned ] || continue
    while pgrep -f "mix_simple.py|guardrails.py|master.sh|pytest" >/dev/null; do sleep 60; done
    bash src/cleanup_after_build.sh >> deliver/cleanup.log 2>&1; touch $d/.cleaned
    echo "- $(date +%H:%M) ET: [cleanup after $(basename $d)] $(tail -n1 deliver/cleanup.log)" >> PROGRESS_mix06.md
  done
  [ -f deliver/06/.cleaned ] && [ -f deliver/05-v2/.cleaned ] && exit
  sleep 120
done
