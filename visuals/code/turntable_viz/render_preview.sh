#!/usr/bin/env bash
# Twin-turntable preview render. Run via: /workspace/mixes/jobs/runjob.sh turntable-preview bash visuals/code/turntable_viz/render_preview.sh
# env: TIMING MIX OUT WORKERS (default 3) GLOPT ('{"shadow":1024}')
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
TIMING=${TIMING:-/workspace/mixes/deliver/visuals/beatgrid_preview.timing.json}
MIX=${MIX:-/workspace/mixes/deliver/07/dj-mix-07-128k.mp3}
OUT=${OUT:-/workspace/mixes/deliver/visuals/turntable_preview.mp4}
WORKERS=${WORKERS:-3}; GLOPT=${GLOPT:-'{"shadow":1024}'}
SCR=$(mktemp -d /workspace/mixes/visuals/tt_scratch_XXXX)
trap 'rm -rf "$SCR"' EXIT
t0=$(date +%s)
python3 "$HERE/prep.py" --timing "$TIMING" --mix "$MIX" --out "$SCR/data.json"
read N FPS SS < <(python3 -c "import json;d=json.load(open('$SCR/data.json'));print(d['frames'],d['fps'],d['mixOffset'])")
echo "frames=$N fps=$FPS mix_offset=$SS workers=$WORKERS"
per=$(( (N + WORKERS - 1) / WORKERS )); pids=()
for w in $(seq 0 $((WORKERS - 1))); do
  a=$((w * per)); b=$(( (w + 1) * per )); [ $b -gt $N ] && b=$N
  node "$HERE/render.mjs" --data "$SCR/data.json" --out "$SCR/part$w.mp4" --from $a --to $b --gl "$GLOPT" > "$SCR/w$w.log" 2>&1 &
  pids+=($!)
done
fail=0
while :; do
  alive=0; for p in "${pids[@]}"; do kill -0 $p 2>/dev/null && alive=1; done
  for w in $(seq 0 $((WORKERS - 1))); do echo "  w$w: $(grep -v '404' "$SCR/w$w.log" | tail -1)"; done
  [ $alive = 0 ] && break; sleep 60
done
for p in "${pids[@]}"; do wait $p || fail=1; done
[ $fail = 0 ] || { echo "worker failed"; cat "$SCR"/w*.log; exit 1; }
for w in $(seq 0 $((WORKERS - 1))); do echo "file '$SCR/part$w.mp4'" >> "$SCR/list.txt"; done
DUR=$(python3 -c "print($N/$FPS)")
ffmpeg -y -loglevel error -f concat -safe 0 -i "$SCR/list.txt" -ss "$SS" -t "$DUR" -i "$MIX" -map 0:v -map 1:a -c:v copy -c:a aac -b:a 192k -shortest -movflags +faststart "$OUT"
STILL_F=${STILL_F:-745}
node "$HERE/render.mjs" --data "$SCR/data.json" --still $STILL_F --png "${OUT%.mp4}.png" --gl "$GLOPT" 2>&1 | grep -v 404 || true
t1=$(date +%s); wall=$((t1 - t0))
python3 -c "d=$N/$FPS; w=$wall; print(f'TURNTABLE_DONE clip={d:.1f}s wall={w}s speed={d/w:.3f}x realtime  est_60min={60/(d/w)/60:.1f}h  (workers=$WORKERS)')"
ffprobe -v error -show_entries format=duration:stream=codec_name,width,height -of compact "$OUT"
