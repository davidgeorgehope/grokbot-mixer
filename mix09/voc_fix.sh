#!/usr/bin/env bash
# Mix 09 RCA fix: protrans-prepped tracks had stand-in voc/drums/bass bar features (constant -100 voc). Run the add_track.sh demucs+barfeats step for them.
set -euo pipefail
cd /workspace/mixes/src2
for b in "$@"; do
  cp st/$b.json st/$b.json.prefix_bak
  T=$(mktemp -d); python3 -m demucs -n htdemucs -j 8 -o "$T" "st/$b.wav" >/dev/null 2>&1
  ls "$T/htdemucs/$b"
  SEP="$T/htdemucs" BF="st/$b.json" python3 barfeats.py | cut -c1-160
  rm -rf "$T"
done
python3 -c "
import json,numpy as np,sys
for b in sys.argv[1:]:
  g=json.load(open(f'st/{b}.json'))['bar'];print(b,{k:(round(min(v),1),round(max(v),1)) for k,v in g.items()})
" "$@"
