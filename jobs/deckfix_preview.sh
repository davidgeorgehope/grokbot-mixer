#!/usr/bin/env bash
set -euo pipefail
cd /workspace/mixes
export META=src2/mix08_r11c_meta.json MIX=deliver/08/dj-mix-08-128k.mp3 TRACKLIST=deliver/08/dj-mix-08-tracklist.md P=${P:-2} CH=${CH:-320} WORK=/workspace/mixes/visuals/tt_prev_wK9Z KEEP_WORK=1
TT=visuals/code/turntable_viz
FROM=780 TO=822 OUT=deliver/viz_preview/deckfix_fx_preview.mp4 FX_RECORD_SWAP=1 FX_LIGHTS=1 bash $TT/preview_window.sh
rm -f "$WORK"/p0*; KEEP_WORK=0 FROM=793 TO=815 OUT=deliver/viz_preview/deckfix_only.mp4 FX_RECORD_SWAP=0 FX_LIGHTS=0 bash $TT/preview_window.sh
echo ALL_PREVIEWS_DONE
