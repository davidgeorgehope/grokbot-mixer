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
# L4 is the proven WebGL2 renderer at $0.59/hr; 4090 as fallback. Secure cloud has direct SSH.
export GPU_CANDIDATES=${GPU_CANDIDATES:-NVIDIA L4|NVIDIA GeForce RTX 4090}
export CLOUD_CANDIDATES=${CLOUD_CANDIDATES:-SECURE}
# RESUME_POD=<id> in the environment reuses a running pod + its work dir.
export RESUME_POD=${RESUME_POD:-}
bash /workspace/mixes/visuals/code/turntable_viz/runpod_render.sh
# confirm duration vs audio after a successful render
ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT"
ffprobe -v error -show_entries format=duration -of csv=p=0 "$MIX"
# leftover-pod check is inside the script (always terminates). Surface the cost line.
