#!/usr/bin/env bash
# Render a short window of a full mix's turntable visual on the box CPU (cheap previews, no GPU).
# usage: META=... MIX=... TRACKLIST=... FROM=780 TO=822 OUT=x.mp4 [FX_RECORD_SWAP=1 FX_LIGHTS=1] [P=4] preview_window.sh
# FROM/TO are mix seconds. Builds segments (with the deck-rule gate), preps only the segments that overlap the
# window, renders their frames in parallel chunks, concatenates, and muxes the mix audio for that window.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
: "${META:?}" "${MIX:?}" "${FROM:?}" "${TO:?}" "${OUT:?}"
P=${P:-4}; FPS=${FPS:-30}; CH=${CH:-150}
WORK=${WORK:-$(mktemp -d /workspace/mixes/visuals/tt_prev_XXXX)}
TL=(); [ -n "${TRACKLIST:-}" ] && TL=(--tracklist "$TRACKLIST")
python3 "$HERE/build_segs.py" "$META" "$MIX" "$WORK/segs" --fps "$FPS" "${TL[@]}" | tail -2
OPTS=$(GROOVE_DIVE=${GROOVE_DIVE:-0} python3 -c "import json,os;e=os.environ.get;print(json.dumps({'dive':e('GROOVE_DIVE','0')=='1','fxSwap':e('FX_RECORD_SWAP','0')=='1','fxLights':e('FX_LIGHTS','0')=='1'}))")
echo "opts=$OPTS window=${FROM}-${TO}s work=$WORK"
python3 - "$WORK" "$FROM" "$TO" "$FPS" "$CH" > "$WORK/jobs.txt" <<'PY'
import json, sys, math
w, a, b, fps, ch = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
S = json.load(open(f'{w}/segs/segs.json')); n = 0
for s in S['segs']:
    lo, hi = max(a, s['t0']), min(b, s['t1'])
    if hi <= lo: continue
    f0, f1 = round((lo - s['t0']) * fps), round((hi - s['t0']) * fps)
    for c in range(f0, f1, ch):
        print(s['tag'], s['timing'], c, min(f1, c + ch), f'{n:04d}'); n += 1
PY
for tag in $(awk '{print $1}' "$WORK/jobs.txt" | uniq); do
  tim=$(awk -v t="$tag" '$1==t{print $2; exit}' "$WORK/jobs.txt")
  [ -s "$WORK/$tag.data.json" ] || GROOVE_DIVE=${GROOVE_DIVE:-0} python3 "$HERE/prep.py" --timing "$tim" --mix "$MIX" --out "$WORK/$tag.data.json" --fps "$FPS" \
    --st "${ST_DIR:-/workspace/mixes/src2/st}" --src "${SRC_DIR:-/workspace/mixes/src2}" | tail -1
done
export HERE WORK OPTS
xargs -P "$P" -L 1 bash -c 'node "$HERE/render.mjs" --data "$WORK/$0.data.json" --out "$WORK/p$4.mp4" --from $2 --to $3 --backend cpu --gl "{\"shadow\":1024}" --opts "$OPTS" > "$WORK/p$4.log" 2>&1 && echo "chunk $4 ok" || { echo "chunk $4 FAILED"; tail -5 "$WORK/p$4.log"; exit 255; }' < "$WORK/jobs.txt"
: > "$WORK/list.txt"; for f in $(ls "$WORK"/p*.mp4 | sort); do echo "file '$f'" >> "$WORK/list.txt"; done
mkdir -p "$(dirname "$OUT")"
ffmpeg -nostdin -y -loglevel error -f concat -safe 0 -i "$WORK/list.txt" -ss "$FROM" -t "$(python3 -c "print($TO-$FROM)")" -i "$MIX" \
  -map 0:v -map 1:a -c:v copy -c:a aac -b:a 192k -shortest -movflags +faststart "$OUT" </dev/null
ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT" | sed 's/^/PREVIEW_DONE dur=/'
[ "${KEEP_WORK:-0}" = 1 ] || rm -rf "$WORK"
