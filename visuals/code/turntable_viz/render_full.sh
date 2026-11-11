#!/usr/bin/env bash
# Full-mix (or single-clip) twin-turntable render. Restartable via WORK dir checkpoints.
#
# Modes:
#   1) Full mix from engine meta:
#        META=... MIX=... OUT=... [TRACKLIST=...] bash render_full.sh
#   2) Single timing clip (preview / one blend):
#        TIMING=... MIX=... OUT=... bash render_full.sh
#
# env:
#   WORK          checkpoint dir (kept across resumes; deleted on success unless KEEP_WORK=1)
#   WORKERS       parallel chrome workers (default 1 on GPU, 3 on CPU)
#   CHUNK_FRAMES  frames per checkpoint part (default 900 = 30s @30fps)
#   BACKEND       auto|gpu|cpu (default auto; runpod sets gpu)
#   GLOPT         JSON for render.mjs --gl (default {"shadow":1024})
#   GROOVE_DIVE   1 to enable needle swoops (default 1); 0 locks the booth cam
#   FORCE_DIVE    1 to plant a mid-clip dive when prep finds none (preview testing)
#   STILL_F       optional still frame after the render
#   KEEP_WORK     1 to keep WORK on success
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
cd /workspace/mixes
MIX=${MIX:?set MIX to the mix mp3/wav}
OUT=${OUT:?set OUT to the destination mp4}
BACKEND=${BACKEND:-auto}
GLOPT=${GLOPT:-'{"shadow":1024}'}
CHUNK_FRAMES=${CHUNK_FRAMES:-900}
GROOVE_DIVE=${GROOVE_DIVE:-1}
FORCE_DIVE=${FORCE_DIVE:-0}
FPS=${FPS:-30}
WORK=${WORK:-/workspace/mixes/visuals/tt_work_$(date +%Y%m%d_%H%M%S)}
mkdir -p "$WORK"
if [ -z "${WORKERS:-}" ]; then
  if [ "$BACKEND" = gpu ]; then WORKERS=1; else WORKERS=3; fi
fi
export TT_BACKEND=$BACKEND
OPTS_JSON=$(GROOVE_DIVE=$GROOVE_DIVE python3 -c "import json,os;print(json.dumps({'dive':os.environ.get('GROOVE_DIVE','1')=='1'}))")

log() { printf '[render_full] %s\n' "$*"; }

if [ -n "${TIMING:-}" ]; then
  mkdir -p "$WORK/segs"
  cp "$TIMING" "$WORK/segs/seg00.timing.json"
  python3 -c "
import json
t=json.load(open('$WORK/segs/seg00.timing.json'))
bs=float(t['bar_sec']); s0=float(t['clip_start_bar']); s1=float(t['clip_end_bar']); dur=(s1-s0)*bs
json.dump({'meta':None,'mix':'$MIX','bar_sec':bs,'fps':$FPS,'cut':[0.0,dur],
  'segs':[{'tag':'seg00','t0':0.0,'t1':dur,'dur':dur,'timing':'$WORK/segs/seg00.timing.json'}]},
  open('$WORK/segs.json','w'), indent=1)
print(f'single timing clip {dur:.1f}s')
"
elif [ -n "${META:-}" ]; then
  TL_ARG=(); [ -n "${TRACKLIST:-}" ] && TL_ARG=(--tracklist "$TRACKLIST")
  python3 "$HERE/build_segs.py" "$META" "$MIX" "$WORK/segs" --fps "$FPS" "${TL_ARG[@]}"
  cp "$WORK/segs/segs.json" "$WORK/segs.json"
else
  echo "set META=... or TIMING=..." >&2; exit 2
fi

NSEG=$(python3 -c "import json;print(len(json.load(open('$WORK/segs.json'))['segs']))")
log "work=$WORK backend=$BACKEND workers=$WORKERS chunks=$CHUNK_FRAMES segs=$NSEG dive=$GROOVE_DIVE"
t0=$(date +%s)

render_seg() {
  local tag=$1 timing=$2
  local sdir="$WORK/$tag"
  mkdir -p "$sdir"
  if [ -s "$sdir/video.mp4" ] && [ -s "$sdir/done.marker" ]; then
    log "$tag: checkpoint hit"; return 0
  fi
  if [ ! -s "$sdir/data.json" ]; then
    FORCE_DIVE=$FORCE_DIVE GROOVE_DIVE=$GROOVE_DIVE \
      python3 "$HERE/prep.py" --timing "$timing" --mix "$MIX" --out "$sdir/data.json" --fps "$FPS" \
        --st "${ST_DIR:-/workspace/mixes/src2/st}" --src "${SRC_DIR:-/workspace/mixes/src2}"
  fi
  local N FPS_R SS
  read N FPS_R SS < <(python3 -c "import json;d=json.load(open('$sdir/data.json'));print(d['frames'],d['fps'],d['mixOffset'])")
  local nchunks=$(( (N + CHUNK_FRAMES - 1) / CHUNK_FRAMES ))
  log "$tag: frames=$N chunks=$nchunks offset=${SS}s"
  local ci=0
  while [ $ci -lt $nchunks ]; do
    local pids=() specs=() fail=0 w=0
    while [ $w -lt $WORKERS ] && [ $ci -lt $nchunks ]; do
      local a=$((ci * CHUNK_FRAMES)) b=$(( (ci + 1) * CHUNK_FRAMES ))
      [ $b -gt $N ] && b=$N
      local part="$sdir/part$(printf '%04d' $ci).mp4"
      if [ -s "$part" ]; then
        log "  $tag part $ci: checkpoint hit"
      else
        specs+=("$ci $a $b $part")
      fi
      ci=$((ci + 1)); w=$((w + 1))
    done
    for spec in "${specs[@]:-}"; do
      [ -z "${spec:-}" ] && continue
      local idx a b part
      read -r idx a b part <<<"$spec"
      log "  $tag part $idx: frames $a-$b"
      (
        node "$HERE/render.mjs" --data "$sdir/data.json" --out "$part.tmp.mp4" --from "$a" --to "$b" \
          --backend "$BACKEND" --gl "$GLOPT" --opts "$OPTS_JSON" > "$sdir/w$idx.log" 2>&1
        mv "$part.tmp.mp4" "$part"
      ) &
      pids+=($!)
    done
    for p in "${pids[@]:-}"; do
      wait "$p" || { fail=1; log "  worker failed"; tail -40 "$sdir"/w*.log || true; }
    done
    [ $fail -eq 0 ] || return 1
  done
  local j=0
  local list="$sdir/list.txt"; : > "$list"
  while [ $j -lt $nchunks ]; do
    local part="$sdir/part$(printf '%04d' $j).mp4"
    [ -s "$part" ] || { log "missing part $j"; return 1; }
    echo "file '$part'" >> "$list"
    j=$((j + 1))
  done
  local DUR; DUR=$(python3 -c "print($N/$FPS_R)")
  # ffmpeg reads stdin for interactive cmds unless -nostdin; otherwise the first
  # mux consumes the rest of seg_list (Mix 08 failed this way, 2026-11-10).
  ffmpeg -nostdin -y -loglevel error -f concat -safe 0 -i "$list" -c copy "$sdir/video.mp4" </dev/null
  # per-seg mux is optional listening aid; final pass remuxes the whole mix
  # SKIP_AUDIO_MUX=1: leave video-only (the host remuxes the master after pull).
  if [ "${SKIP_AUDIO_MUX:-0}" != 1 ]; then
    ffmpeg -nostdin -y -loglevel error -i "$sdir/video.mp4" -ss "$SS" -t "$DUR" -i "$MIX" \
      -map 0:v -map 1:a -c:v copy -c:a aac -b:a 192k -shortest -movflags +faststart "$sdir/done.mp4" </dev/null
  fi
  echo ok > "$sdir/done.marker"
  log "$tag: done (${DUR}s)"
}

python3 -c "import json;d=json.load(open('$WORK/segs.json'));
[print(s['tag']+'\t'+s['timing']) for s in d['segs']]" > "$WORK/seg_list.txt"

while IFS=$'\t' read -r tag timing <&3; do
  render_seg "$tag" "$timing"
done 3< "$WORK/seg_list.txt"

: > "$WORK/final_list.txt"
while IFS=$'\t' read -r tag timing <&3; do
  echo "file '$WORK/$tag/video.mp4'" >> "$WORK/final_list.txt"
done 3< "$WORK/seg_list.txt"
TOTAL=$(python3 -c "import json;d=json.load(open('$WORK/segs.json'));print(d['cut'][-1])")
ffmpeg -nostdin -y -loglevel error -f concat -safe 0 -i "$WORK/final_list.txt" -c copy "$WORK/video_all.mp4" </dev/null
mkdir -p "$(dirname "$OUT")"
if [ "${SKIP_AUDIO_MUX:-0}" = 1 ]; then
  # Video-only output; runpod_render.sh muxes MASTER locally at 320k AAC.
  ffmpeg -nostdin -y -loglevel error -i "$WORK/video_all.mp4" -c:v copy -an -movflags +faststart "$OUT" </dev/null
else
  ffmpeg -nostdin -y -loglevel error -i "$WORK/video_all.mp4" -t "$TOTAL" -i "$MIX" \
    -map 0:v -map 1:a -c:v copy -c:a aac -b:a 192k -shortest -movflags +faststart "$OUT" </dev/null
fi
if [ -n "${STILL_F:-}" ]; then
  FIRST=$(awk -F'\t' 'NR==1{print $1}' "$WORK/seg_list.txt")
  node "$HERE/render.mjs" --data "$WORK/$FIRST/data.json" --still "$STILL_F" --png "${OUT%.mp4}.png" \
    --backend "$BACKEND" --gl "$GLOPT" --opts "$OPTS_JSON" 2>&1 | grep -v 404 || true
fi
t1=$(date +%s); wall=$((t1 - t0))
ffprobe -v error -show_entries format=duration:stream=codec_name,width,height -of compact "$OUT" || true
python3 -c "d=float('$TOTAL'); w=$wall; print(f'TURNTABLE_FULL_DONE clip={d:.1f}s wall={w}s speed={d/max(w,1):.3f}x realtime  est_60min={60/(d/max(w,1))/60:.2f}h  backend=$BACKEND workers=$WORKERS')"
if [ "${KEEP_WORK:-0}" = 1 ]; then log "KEEP_WORK=1, left $WORK"; else log "cleaning $WORK"; rm -rf "$WORK"; fi
