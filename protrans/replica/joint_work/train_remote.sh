#!/usr/bin/env bash
# Train the joint picker on the home training Mac (run from the box). Host alias: TRAIN_HOST in config.env.
# Workers are sized from the Mac's free RAM: measured ~0.85 GB per LightGBM fit worker (11-27).
# usage: train_remote.sh <cmd: cv|train|stab> [JOINT_K]
set -euo pipefail
[ -z "${TRAIN_HOST:-}" ] && . /workspace/mixes/config.env
H="${TRAIN_HOST:?set TRAIN_HOST in config.env}"
CMD=${1:-train}; K=${2:-8}; PER_WORKER_MB=${PER_WORKER_MB:-900}
SSH="ssh -o ControlMaster=no -o ControlPath=none $H"
SCP="scp -q -o ControlMaster=no -o ControlPath=none"
L=/workspace/mixes/protrans/replica
$SCP "$L/joint_picker.py" "$H:grokbot-mixer-train/"
$SCP "$L/joint_work/feats.npz" "$L/joint_work/meta.json" "$H:grokbot-mixer-train/joint_work/"
read -r FREE_MB NCPU < <($SSH 'echo $(( $(vm_stat | awk "/Pages free|Pages inactive|Pages speculative/ {gsub(\"\\\\.\",\"\",\$NF); s+=\$NF} END {print s}") * 16384 / 1048576 )) $(sysctl -n hw.ncpu)')
WK=$(( FREE_MB / 2 / PER_WORKER_MB )); MAXW=$(( NCPU - 2 )); [ "$WK" -gt "$MAXW" ] && WK=$MAXW; [ "$WK" -lt 1 ] && WK=1
echo "free ${FREE_MB} MB, ${NCPU} cores -> ${WK} workers (~${PER_WORKER_MB} MB each)"
$SSH "cd ~/grokbot-mixer-train && rm -f joint_work/X32.npy && OMP_NUM_THREADS=1 JOINT_K=$K JOINT_WORKERS=$WK ./venv/bin/python joint_picker.py $CMD joint_work > $CMD.log 2>&1; tail -5 $CMD.log"
$SCP -r "$H:grokbot-mixer-train/joint_work/models" "$L/joint_work/" 2>/dev/null || true
$SCP "$H:grokbot-mixer-train/joint_work/cv_oof.json" "$H:grokbot-mixer-train/joint_work/stab_k*.json" "$L/joint_work/" 2>/dev/null || true
