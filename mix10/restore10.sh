#!/usr/bin/env bash
# restore stretched audio caches for the Mix 10 crate (3 in parallel); new Logistics tracks already have st wavs
cd /workspace/mixes/src2
for b in $(cat ../mix10/crate.txt); do ls st/$b*.wav >/dev/null 2>&1 || echo $b; done | xargs -P3 -n1 python3 restore_audio.py
for b in $(cat ../mix10/crate.txt); do ls st/$b*.wav >/dev/null 2>&1 || { echo "MISSING $b"; exit 1; }; done; echo all restored
