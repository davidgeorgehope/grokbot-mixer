#!/usr/bin/env bash
# Train the joint picker on the home training Mac (run from the box). Host alias: TRAIN_HOST in config.env.
# Workers are sized from the Mac's free RAM (memory_pressure free %, which counts reclaimable cache): measured ~0.85 GB per LightGBM fit worker (11-27).
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
read -r FREE_MB NCPU < <($SSH 'echo $(( $(memory_pressure -Q | awk "/free percentage/ {gsub(\"%\",\"\",\$5); print \$5}") * $(sysctl -n hw.memsize) / 100 / 1048576 )) $(sysctl -n hw.ncpu)')
THREADS=1  # LightGBM threads per worker, set explicitly for fit and predict (its default is every core)
WK=$(( FREE_MB / 2 / PER_WORKER_MB ))                      # RAM: half the free memory
MAXW=$(( (NCPU - 4) / THREADS ))                          # CPU: workers x threads <= cores - 4 (headroom for voice/cameras)
[ "$WK" -gt "$MAXW" ] && WK=$MAXW; [ "$WK" -lt 1 ] && WK=1
echo "free ${FREE_MB} MB, ${NCPU} cores -> ${WK} workers x ${THREADS} thread (~${PER_WORKER_MB} MB each)"
ENVS=$(env | grep -E '^(JOINT_(LEN_W|LEAVES|MCS|NEST|L2|TAG)|STAB_TAU)=' | tr '\n' ' ' || true)
$SSH "cd ~/grokbot-mixer-train && rm -f joint_work/X32.npy && rm -f $CMD.done && (nohup env $ENVS OMP_NUM_THREADS=1 JOINT_THREADS=$THREADS JOINT_K=$K JOINT_WORKERS=$WK ./venv/bin/python joint_picker.py $CMD joint_work > $CMD.log 2>&1; echo \$? > $CMD.done) > /dev/null 2>&1 &"
# detached on the Mac: an ssh drop cannot kill it; poll until it writes $CMD.done
until $SSH "test -f ~/grokbot-mixer-train/$CMD.done" 2>/dev/null; do sleep 30; done
$SSH "tail -5 ~/grokbot-mixer-train/$CMD.log; cat ~/grokbot-mixer-train/$CMD.done"
$SCP -r "$H:grokbot-mixer-train/joint_work/models*" "$L/joint_work/" 2>/dev/null || true
$SCP "$H:grokbot-mixer-train/joint_work/cv_oof*.json" "$H:grokbot-mixer-train/joint_work/stab_*.json" "$L/joint_work/" 2>/dev/null || true
