#!/usr/bin/env bash
set -euo pipefail
export META=/workspace/mixes/src2/mix08_r11c_meta.json
export MIX=/workspace/mixes/deliver/08/dj-mix-08-128k.mp3
export MASTER=${MASTER:-/workspace/mixes/src2/mix08_r11c_master.wav}
export TRACKLIST=/workspace/mixes/deliver/08/dj-mix-08-tracklist.md
export OUT=${OUT:-/workspace/mixes/visuals/dj-mix-08-visuals-1080p30.mp4}
export GROOVE_DIVE=1
export SKIP_AUDIO_MUX=1
# Finished segments are copied here as they complete; a retry on a fresh pod resumes from them.
export CKPT_DIR=${CKPT_DIR:-/workspace/tt_viz_ckpt/mix08}
# GPU walk: every type in GPU_CANDIDATES on SECURE, then the same order on COMMUNITY.
# L4 is the proven WebGL2 renderer; pods over MAX_RATE_USD per hour are dropped right after create.
export GPU_CANDIDATES=${GPU_CANDIDATES:-NVIDIA L4|NVIDIA GeForce RTX 4090|NVIDIA RTX A5000|NVIDIA RTX A4000|NVIDIA GeForce RTX 3090|NVIDIA L40S|NVIDIA A40}
export CLOUD_CANDIDATES=${CLOUD_CANDIDATES:-SECURE|COMMUNITY}
export MAX_RATE_USD=${MAX_RATE_USD:-0.90}
# RESUME_POD=<id> in the environment reuses a running pod + its work dir.
export RESUME_POD=${RESUME_POD:-}
# No capacity anywhere (rc 75): wait CAPACITY_RETRY_SEC and walk the list again, up to CAPACITY_WAIT_SEC in total.
CAPACITY_RETRY_SEC=${CAPACITY_RETRY_SEC:-600}
CAPACITY_WAIT_SEC=${CAPACITY_WAIT_SEC:-3600}
t_first=$(date +%s); try=1
while true; do
  rc=0
  bash /workspace/mixes/visuals/code/turntable_viz/runpod_render.sh || rc=$?
  [ "$rc" = 0 ] && break
  if [ "$rc" = 75 ] && [ $(( $(date +%s) - t_first + CAPACITY_RETRY_SEC )) -le "$CAPACITY_WAIT_SEC" ]; then
    echo "[turntable_mix08] no GPU capacity on try $try; retrying in ${CAPACITY_RETRY_SEC}s ($(date))"
    sleep "$CAPACITY_RETRY_SEC"; try=$((try + 1)); continue
  fi
  exit "$rc"
done
# confirm duration vs audio after a successful render
ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT"
ffprobe -v error -show_entries format=duration -of csv=p=0 "$MIX"
# leftover-pod check is inside the script (always terminates). Surface the cost line.
