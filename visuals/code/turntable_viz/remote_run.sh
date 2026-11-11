#!/usr/bin/env bash
# Runs on the Runpod GPU box. Expects payload at $TT_ROOT (default /workspace/tt_viz).
# Launched detached by remote_detach.sh (never in the foreground of an ssh session).
# RESUME=1 reuses $TT_ROOT/work: finished segments and valid chunk parts are kept.
set -euo pipefail
TT_ROOT=${TT_ROOT:-/workspace/tt_viz}
HERE=$TT_ROOT/turntable_viz
log() { printf '[remote_run] %s\n' "$*"; }

export NVIDIA_DRIVER_CAPABILITIES="${NVIDIA_DRIVER_CAPABILITIES:-compute,utility,graphics,display,video}"
export NVIDIA_VISIBLE_DEVICES="${NVIDIA_VISIBLE_DEVICES:-all}"
export __NV_PRIME_RENDER_OFFLOAD=1
export __GLX_VENDOR_LIBRARY_NAME=nvidia

cd "$HERE"
# RESUME=1 on a pod that already bootstrapped: skip the apt/chrome install.
if [ "${RESUME:-0}" = 1 ] && [ -f /tmp/tt_gl_env.sh ] && command -v node >/dev/null \
   && { command -v google-chrome-stable || command -v google-chrome || command -v chromium; } >/dev/null; then
  log "resume: bootstrap already done on this pod, skipping"
else
  bash bootstrap_runpod.sh
fi
# shellcheck disable=SC1091
[ -f /tmp/tt_gl_env.sh ] && source /tmp/tt_gl_env.sh
export CHROME_PATH=$(command -v google-chrome-stable || command -v google-chrome || command -v chromium-browser || command -v chromium)

# Probe WebGL backends; pick the first hardware one.
log "probing WebGL2 backends"
set +e
PROBE_OUT=$(node "$HERE/probe_webgl.mjs" 2>&1)
PROBE_RC=$?
set -e
printf '%s\n' "$PROBE_OUT"
if [ $PROBE_RC -ne 0 ]; then
  echo "FATAL: no hardware WebGL2 on this pod (probe rc=$PROBE_RC)" >&2
  exit 3
fi
BACKEND_NAME=$(printf '%s\n' "$PROBE_OUT" | awk -F= '/PROBE_OK/{print $2}' | awk '{print $1}')
# PROBE_OK backend=egl renderer=...
BACKEND_NAME=$(printf '%s\n' "$PROBE_OUT" | sed -n 's/.*PROBE_OK backend=\([^ ]*\).*/\1/p' | tail -1)
export TT_GL=${TT_GL_OVERRIDE:-$BACKEND_NAME}
export TT_BACKEND=gpu
log "using TT_GL=$TT_GL"

mkdir -p /workspace/mixes/visuals/code
ln -sfn "$HERE" /workspace/mixes/visuals/code/turntable_viz
ln -sfn "$TT_ROOT/beatgrid_viz.py" /workspace/mixes/visuals/code/beatgrid_viz.py

# Analysis + source audio live under $TT_ROOT on the pod, not /workspace/mixes/src2.
# render_full.sh honors ST_DIR/SRC_DIR (no sed). Symlinks cover the default paths too.
export ST_DIR=$TT_ROOT/st SRC_DIR=$TT_ROOT/src
mkdir -p /workspace/mixes/src2
ln -sfn "$ST_DIR" /workspace/mixes/src2/st
# Default --src is /workspace/mixes/src2; link each packed audio into place as a fallback.
for f in "$SRC_DIR"/*; do
  [ -e "$f" ] || continue
  ln -sfn "$f" "/workspace/mixes/src2/$(basename "$f")"
done
missing=0
for j in "$ST_DIR"/*.json; do
  [ -e "$j" ] || missing=1
done
# Fail closed if this mix's analysis files did not arrive in the payload.
if [ ! -d "$ST_DIR" ] || [ "$missing" = 1 ] || ! ls "$ST_DIR"/*.json >/dev/null 2>&1; then
  echo "FATAL: no analysis json under $ST_DIR" >&2
  ls -la "$ST_DIR" "$TT_ROOT" >&2 || true
  exit 2
fi
log "st=$ST_DIR src=$SRC_DIR analysis_json=$(ls -1 "$ST_DIR"/*.json | grep -v sections | wc -l | tr -d ' ')"

OUT=$TT_ROOT/out.mp4
WORK=$TT_ROOT/work
mkdir -p "$WORK"

if [ -f "$TT_ROOT/timing.json" ]; then
  log "mode=timing"
  TIMING="$TT_ROOT/timing.json" MIX="$TT_ROOT/mix.audio" OUT="$OUT" WORK="$WORK" \
    BACKEND=gpu CHUNK_FRAMES="${CHUNK_FRAMES:-900}" GROOVE_DIVE="${GROOVE_DIVE:-1}" \
    FORCE_DIVE="${FORCE_DIVE:-0}" KEEP_WORK=1 WORKERS="${WORKERS:-1}" \
    bash "$HERE/render_full.sh"
elif [ -f "$TT_ROOT/meta.json" ]; then
  log "mode=meta"
  TL_ENV=()
  [ -f "$TT_ROOT/tracklist.md" ] && TL_ENV+=(TRACKLIST="$TT_ROOT/tracklist.md")
  env META="$TT_ROOT/meta.json" MIX="$TT_ROOT/mix.audio" OUT="$OUT" WORK="$WORK" \
    BACKEND=gpu CHUNK_FRAMES="${CHUNK_FRAMES:-900}" GROOVE_DIVE="${GROOVE_DIVE:-1}" \
    FORCE_DIVE="${FORCE_DIVE:-0}" KEEP_WORK=1 WORKERS="${WORKERS:-1}" \
    "${TL_ENV[@]}" \
    bash "$HERE/render_full.sh"
else
  echo "no timing.json or meta.json in $TT_ROOT" >&2; exit 2
fi
ffprobe -v error -show_entries format=duration:stream=codec_name,width,height -of compact "$OUT"
log "wrote $OUT"
