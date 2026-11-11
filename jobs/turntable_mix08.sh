#!/usr/bin/env bash
set -euo pipefail
export META=/workspace/mixes/src2/mix08_r11c_meta.json
export MIX=/workspace/mixes/deliver/08/dj-mix-08-128k.mp3
export TRACKLIST=/workspace/mixes/deliver/08/dj-mix-08-tracklist.md
export OUT=/workspace/mixes/visuals/dj-mix-08-visuals-1080p30.mp4
export GROOVE_DIVE=1
bash /workspace/mixes/visuals/code/turntable_viz/runpod_render.sh
# confirm duration vs audio after a successful render
ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT"
ffprobe -v error -show_entries format=duration -of csv=p=0 "$MIX"
# leftover-pod check is inside the script (always terminates). Surface the cost line.
