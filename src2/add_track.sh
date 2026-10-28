#!/usr/bin/env bash
# Prep new tracks for the crossfader engine. Run in src2/ after copying <ID>.m4a here.
# usage: bash add_track.sh <ID> [<ID> ...]
# Per track: decode -> true BPM -> stretch to 174 + grid (st/<ID>.wav/.json) -> key -> per-bar features
# (vocal/drum bars come from demucs stems that are deleted right after) -> local phase check.
set -euo pipefail
cd "$(dirname "$0")"; mkdir -p wav st
for b in "$@"; do
  [ -f "wav/$b.wav" ] || ffmpeg -loglevel error -y -i "$b.m4a" -ar 44100 -ac 2 "wav/$b.wav"
  B=$(python3 pbpm.py "wav/$b.wav" 2>/dev/null | awk '{print $2}'); echo "$b BPM $B"
  python3 prep.py "wav/$b.wav" "$B" 2>&1 | grep -vE "Warn|mel|Using|NOTE" || true
  python3 - "$b" <<'PY' 2>&1 | grep -v INFO
import sys,essentia.standard as es
exec(open('keys.py').read().split("src=")[0])
a=es.MonoLoader(filename=f'st/{sys.argv[1]}.wav',sampleRate=44100)()
print('KEY',sys.argv[1],[CAM[es.KeyExtractor(profileType=p,sampleRate=44100)(a)[:2]] for p in ['edma','bgate','krumhansl','temperley']])
PY
  T=$(mktemp -d); python3 -m demucs -n htdemucs -j 8 -o "$T" "st/$b.wav" >/dev/null 2>&1
  python3 fixgrid.py >/dev/null 2>&1
  SEP="$T/htdemucs" BF="st/$b.json" python3 barfeats.py | cut -c1-120
  rm -rf "$T"
  python3 phasechk.py "$b" 2>&1 | tail -3
done
echo "Add each new key to src/tests/keys_extra.json (id -> Camelot) and keys_full.json."
