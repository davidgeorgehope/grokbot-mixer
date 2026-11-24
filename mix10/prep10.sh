#!/usr/bin/env bash
# Mix 10 prep: Logistics (Hospital) tracks that only had protrans prep (stand-in voc/drums/bass bar features).
# Runs the add_track.sh key + demucs + barfeats + phase-check steps (grid/stretch from prep kept). Backups st/<id>.json.prefix_bak
set -uo pipefail
cd /workspace/mixes/src2
for b in "$@"; do
  echo "== $b $(date +%T)"
  [ -f st/$b.json.prefix_bak ] || cp st/$b.json st/$b.json.prefix_bak
  python3 - "$b" <<'PY' 2>&1 | grep -v INFO
import sys,essentia.standard as es
exec(open('keys.py').read().split("src=")[0])
a=es.MonoLoader(filename=f'st/{sys.argv[1]}.wav',sampleRate=44100)()
print('KEY',sys.argv[1],[CAM[es.KeyExtractor(profileType=p,sampleRate=44100)(a)[:2]] for p in ['edma','bgate','krumhansl','temperley']])
PY
  T=$(mktemp -d); python3 -m demucs -n htdemucs -j 8 -o "$T" "st/$b.wav" >/dev/null 2>&1
  ls "$T/htdemucs/$b" || { echo "demucs failed $b"; exit 1; }
  SEP="$T/htdemucs" BF="st/$b.json" python3 barfeats.py | cut -c1-160
  rm -rf "$T"
  python3 phasechk.py "$b" 2>&1 | tail -3
done
python3 -c "
import json,sys
for b in sys.argv[1:]:
  g=json.load(open(f'st/{b}.json'))['bar'];print(b,{k:(round(min(v),1),round(max(v),1)) for k,v in g.items()})
" "$@"
