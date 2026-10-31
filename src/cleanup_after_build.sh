#!/usr/bin/env bash
# Auto-cleanup after a delivery (the listener 2026-10-31: every job cleans up after itself).
# Keeps: m4a/flac sources, st/*.json + feature npy/npz, guard_*/ json+png, *_meta/_qa/_ears json, plans, ratings, final deliverables.
# Removes: stems st/*.wav (except st/KEEP_STEMS.txt ids), decoded wav/, *_raw.wav, *_master.wav, test/A-B renders (tmp_*, /tmp mix renders).
# Regenerate with: python3 src2/restore_audio.py   (bit-exact). usage: cleanup_after_build.sh [--dry]
set -uo pipefail; cd "$(dirname "$0")/../src2"; DRY=${1:-}
before=$(du -sk . | cut -f1); keep=$(cat st/KEEP_STEMS.txt 2>/dev/null)
list(){ for f in st/*.wav; do b=$(basename "$f" .wav); [[ " $keep " == *" $b "* ]] || echo "$f"; done
        ls st/*_in.wav wav/*.wav *_raw.wav *_master.wav *_dry_raw.wav ../tmp_*.mp3 ../tmp_*.wav 2>/dev/null; }
if [ "$DRY" = --dry ]; then list | sort -u; exit 0; fi
for b in $(ls st/*.json | xargs -n1 basename | sed 's/\.json$//'); do [ -e "wav/$b.wav" ] && [ ! -e "./$b.m4a" ] && [ ! -e "./$b.flac" ] && ffmpeg -loglevel error -y -i "wav/$b.wav" "./$b.flac"; done  # never delete the only copy
list | sort -u | while read -r f; do rm -f -- "$f"; done
after=$(du -sk . | cut -f1); echo "CLEANUP freed $(( (before-after)/1024 )) MB"
