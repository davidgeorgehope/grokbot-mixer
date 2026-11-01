#!/bin/bash
# Re-fetch the studio source tracks used by control_curves.py (ids in pro_sets/src/*/NN.info, first line = id|title|sec).
# Audio is deleted after each run (scratch); the .info files pin the exact YouTube uploads.
cd /workspace/mixes/pro_sets/src
for f in */*.info; do id=$(head -1 "$f" | cut -d'|' -f1); o=${f%.info}; [ -f "$o.m4a" ] || yt-dlp -q -f bestaudio -x --audio-format m4a -o "$o.%(ext)s" -- "$id"; done
