#!/usr/bin/env bash
# Sourced by runpod_render.sh. Box-side copy of finished render segments, so a
# lost pod never loses finished work (Mix 08 r4 lost seg00-seg07 this way).
#
# Needs from the caller: SSH (array), TARGET, CKPT_DIR, HERE, log(), run_wait().
#   ckpt_prepare        create CKPT_DIR; move it aside if the render inputs changed
#   ckpt_count          number of valid finished segments on the box
#   ckpt_push           send box checkpoints into a fresh pod's work dir
#   ckpt_pull_new       pull segments the pod finished since the last pull
#   ckpt_assemble OUT   build the video-only mp4 from box checkpoints (pull fallback)
#
# Layout (mirrors the pod's work dir): segs.json seg_list.txt segs/ <tag>/{data.json,video.mp4,done.marker}
REMOTE_WORK=${REMOTE_WORK:-/workspace/tt_viz/work}

_ck_frames() {
  local n
  n=$(ffprobe -v error -select_streams v:0 -count_packets -show_entries stream=nb_read_packets \
        -of default=nw=1:nk=1 "$1" 2>/dev/null </dev/null | head -1)
  case "$n" in ''|*[!0-9]*) echo 0 ;; *) echo "$n" ;; esac
}

_ck_seg_ok() {  # dir -> 0 if video.mp4 frame count matches data.json
  local d=$1 want have
  [ -s "$d/video.mp4" ] && [ -s "$d/data.json" ] && [ -s "$d/done.marker" ] || return 1
  want=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['frames'])" "$d/data.json" 2>/dev/null || echo -1)
  have=$(_ck_frames "$d/video.mp4")
  [ "$have" = "$want" ]
}

# Everything that changes the pixels of a finished segment.
ckpt_fingerprint() {
  {
    for f in render.mjs scene.js index.html prep.py build_segs.py; do
      [ -f "$HERE/$f" ] && sha256sum "$HERE/$f" | cut -d' ' -f1
    done
    [ -n "${META:-}" ] && sha256sum "$META" | cut -d' ' -f1
    [ -n "${TIMING:-}" ] && sha256sum "$TIMING" | cut -d' ' -f1
    [ -n "${TRACKLIST:-}" ] && [ -f "$TRACKLIST" ] && sha256sum "$TRACKLIST" | cut -d' ' -f1
    sha256sum "$MIX" | cut -d' ' -f1
    echo "dive=${GROOVE_DIVE:-1} force=${FORCE_DIVE:-0} fps=${FPS:-30} gl=${GLOPT:-}"
  } | sha256sum | cut -d' ' -f1
}

ckpt_prepare() {
  local fp old
  fp=$(ckpt_fingerprint)
  mkdir -p "$CKPT_DIR"
  old=$(cat "$CKPT_DIR/fingerprint" 2>/dev/null || true)
  if [ -n "$old" ] && [ "$old" != "$fp" ]; then
    log "ckpt: inputs changed since $CKPT_DIR was written; moving it aside"
    mv "$CKPT_DIR" "$CKPT_DIR.stale.$(date +%Y%m%d%H%M%S)"
    mkdir -p "$CKPT_DIR"
  fi
  echo "$fp" > "$CKPT_DIR/fingerprint"
  # Drop half-written pulls and invalid segments.
  rm -rf "$CKPT_DIR"/.pull.*
  local d
  for d in "$CKPT_DIR"/seg[0-9]*/; do
    [ -d "$d" ] || continue
    _ck_seg_ok "${d%/}" || { log "ckpt: dropping invalid $(basename "$d")"; rm -rf "${d%/}"; }
  done
  log "ckpt: dir=$CKPT_DIR valid_segments=$(ckpt_count)"
}

ckpt_count() {
  local n=0 d
  for d in "$CKPT_DIR"/seg[0-9]*/; do [ -s "${d}done.marker" ] && n=$((n + 1)); done
  echo "$n"
}

ckpt_push() {
  local n
  n=$(ckpt_count)
  [ "$n" -gt 0 ] && [ -s "$CKPT_DIR/segs.json" ] || { log "ckpt: nothing to push"; return 1; }
  log "ckpt: pushing $n finished segments to the pod"
  local out
  out=$(run_wait timeout -k 5 900 bash -c 'tar -C "$1" -cf - --exclude=fingerprint --exclude=".pull.*" . \
      | "${@:4}" "$2" "mkdir -p $3 && tar -C $3 -xf - && echo ckpt_pushed"' _ "$CKPT_DIR" "$TARGET" "$REMOTE_WORK" "${SSH[@]}" 2>&1 || true)
  echo "$out" | grep -q ckpt_pushed || { log "ckpt: push failed: $(echo "$out" | tail -c 200)"; return 2; }
  log "ckpt: push ok"
}

# Pull segments that are finished on the pod but not yet on the box. Not fatal on error.
ckpt_pull_new() {
  local list want=() t tmp out
  list=$(run_wait timeout -k 5 60 "${SSH[@]}" "$TARGET" \
    "cd $REMOTE_WORK 2>/dev/null && for d in seg[0-9]*/; do d=\${d%/}; [ -s \$d/done.marker ] && [ -s \$d/video.mp4 ] && echo \$d; done; true" 2>/dev/null) || return 0
  for t in $list; do
    [ -s "$CKPT_DIR/$t/done.marker" ] || want+=("$t")
  done
  [ ${#want[@]} -gt 0 ] || return 0
  tmp="$CKPT_DIR/.pull.$$"; rm -rf "$tmp"; mkdir -p "$tmp"
  local files="segs.json seg_list.txt segs"
  for t in "${want[@]}"; do files="$files $t/data.json $t/video.mp4 $t/done.marker"; done
  if ! run_wait timeout -k 5 900 bash -c '"${@:4}" "$1" "cd $2 && tar -cf - $3" | tar -C "$0" -xf -' \
       "$tmp" "$TARGET" "$REMOTE_WORK" "$files" "${SSH[@]}" 2>"$tmp.err"; then
    log "ckpt: pull failed (will retry): $(tail -c 200 "$tmp.err" 2>/dev/null)"; rm -rf "$tmp" "$tmp.err"; return 0
  fi
  rm -f "$tmp.err"
  [ -s "$CKPT_DIR/segs.json" ] || { cp "$tmp/segs.json" "$tmp/seg_list.txt" "$CKPT_DIR/"; cp -r "$tmp/segs" "$CKPT_DIR/"; }
  for t in "${want[@]}"; do
    if _ck_seg_ok "$tmp/$t"; then
      rm -rf "$CKPT_DIR/$t"; mkdir -p "$CKPT_DIR/$t"
      mv "$tmp/$t/data.json" "$tmp/$t/video.mp4" "$CKPT_DIR/$t/"
      mv "$tmp/$t/done.marker" "$CKPT_DIR/$t/"   # marker last
    else
      log "ckpt: pulled $t failed validation; will retry"
    fi
  done
  rm -rf "$tmp"
  log "ckpt: box has $(ckpt_count) finished segments"
}

# Video-only concat of all segments from box checkpoints (same as render_full's final pass).
ckpt_assemble() {
  local out=$1 tag timing list
  [ -s "$CKPT_DIR/seg_list.txt" ] || return 1
  list="$CKPT_DIR/.final_list.txt"; : > "$list"
  while IFS=$'\t' read -r tag timing <&3; do
    _ck_seg_ok "$CKPT_DIR/$tag" || { log "ckpt: assemble missing $tag"; return 1; }
    echo "file '$CKPT_DIR/$tag/video.mp4'" >> "$list"
  done 3< "$CKPT_DIR/seg_list.txt"
  ffmpeg -nostdin -y -loglevel error -f concat -safe 0 -i "$list" -c copy -an -movflags +faststart "$out" </dev/null
  rm -f "$list"
}
