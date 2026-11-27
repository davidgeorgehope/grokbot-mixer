#!/usr/bin/env bash
# Train the joint picker on the home training Mac (run FROM THE BOX). Host alias: TRAIN_HOST in config.env. Memory rules: every process < 6 GB
# (the Mac's mem-guard kills above that), total well under 10 GB, nice 10, abort if the Mac's
# free memory drops below 15%. Measured 11-27: ~0.85 GB and ~27 s per LightGBM fit worker.
# usage: train_remote.sh <cmd: cv|train|stab> [JOINT_K] [JOINT_WORKERS]
set -euo pipefail
[ -z "${TRAIN_HOST:-}" ] && . /workspace/mixes/config.env
H="${TRAIN_HOST:?set TRAIN_HOST in config.env}"
CMD=${1:-train}; K=${2:-8}; WK=${3:-4}
SSH="ssh -o ControlMaster=no -o ControlPath=none $H"
L=/workspace/mixes/protrans/replica
rsync -q -e "$SSH" "$L/joint_picker.py" $H:grokbot-mixer-train/ 2>/dev/null || scp -q -o ControlMaster=no -o ControlPath=none "$L/joint_picker.py" $H:grokbot-mixer-train/
scp -q -o ControlMaster=no -o ControlPath=none "$L/joint_work/feats.npz" "$L/joint_work/meta.json" $H:grokbot-mixer-train/joint_work/
$SSH "cd ~/grokbot-mixer-train && rm -f joint_work/X32.npy && OMP_NUM_THREADS=1 JOINT_K=$K JOINT_WORKERS=$WK nohup nice -n 10 ./venv/bin/python joint_picker.py $CMD joint_work > $CMD.log 2>&1 & echo \$! > $CMD.pid"
while true; do
  sleep 20
  out=$($SSH "cd ~/grokbot-mixer-train; kill -0 \$(cat $CMD.pid) 2>/dev/null && echo RUN || echo END; memory_pressure -Q | awk '/free percentage/{print \$5}' | tr -d %; ps -A -o rss,command | awk '/joint_picker/ && !/awk/ {if (\$1>m) m=\$1} END {print int(m/1024)}'")
  st=$(echo "$out" | sed -n 1p); free=$(echo "$out" | sed -n 2p); maxmb=$(echo "$out" | sed -n 3p)
  echo "$(date +%T) $st free=${free}% max_worker=${maxmb}MB"
  if [ "${free:-100}" -lt 15 ] || [ "${maxmb:-0}" -gt 5000 ]; then
    echo "ABORT: memory guard"; $SSH "pkill -f 'joint_picker.py $CMD'"; exit 3
  fi
  [ "$st" = END ] && break
done
$SSH "cat ~/grokbot-mixer-train/$CMD.log | tail -5"
mkdir -p "$L/joint_work"
scp -q -r -o ControlMaster=no -o ControlPath=none "$H:grokbot-mixer-train/joint_work/{models,cv_oof.json,stab_k*.json}" "$L/joint_work/" 2>/dev/null || true
