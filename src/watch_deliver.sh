#!/bin/bash
# watch an autoloop log; on "pytest exit 0" deliver.  usage: watch_deliver.sh LOGGLOB FINAL_NAME_FILE NN MP3 "TITLE"
cd /workspace/mixes
while :; do
  if grep -h "pytest exit 0" $1 >/dev/null 2>&1; then G=$(cut -d' ' -f1 $2); python3 src/deliver.py "$3" /workspace/mixes/src2/${G}_meta.json "$4" "$5"; while pgrep -f "mix_simple.py|guardrails.py|master.sh|pytest" >/dev/null; do sleep 60; done; bash src/cleanup_after_build.sh >> /workspace/mixes/deliver/cleanup.log 2>&1; echo "- $(date +%H:%M) ET: [cleanup after $3] $(tail -n1 /workspace/mixes/deliver/cleanup.log)" >> /workspace/mixes/PROGRESS_mix06.md; exit; fi
  sleep 60
done
