#!/usr/bin/env bash
# Re-run demucs+barfeats for crate tracks missing real vocal features (VOCOFF in the
# planner, but checks.vocal_bars treats missing voc as every bar vocal -> dry V clashes).
# Same method as mix09/voc_fix.sh. Does not loosen any test.
set -euo pipefail
cd /workspace/mixes/src2
mkdir -p /tmp/protrans_work
ids=("$@")
if [ ${#ids[@]} -eq 0 ]; then
  ids=(EpHrodtTiK0 I9QGpHScGug SqzxwPEa-DI zEvLsOVhg0I J3oTRY7AdE4)
fi
for b in "${ids[@]}"; do
  echo "== vocfix $b $(date +%T)"
  # serialize with nightly's per-track lock so we don't clobber each other
  exec 9>/tmp/protrans_work/${b}.lock
  flock 9
  [ -f st/$b.json.mix10_vocfix_bak ] || cp st/$b.json st/$b.json.mix10_vocfix_bak
  T=$(mktemp -d)
  python3 -m demucs -n htdemucs -j 2 -o "$T" "st/$b.wav" >/dev/null
  ls "$T/htdemucs/$b" || { echo "demucs failed $b"; rm -rf "$T"; exit 1; }
  SEP="$T/htdemucs" BF="st/$b.json" python3 barfeats.py | cut -c1-160
  rm -rf "$T"
  flock -u 9
  exec 9>&-
done
python3 - <<'PY' "${ids[@]}"
import json,sys,numpy as np
bad=0
ids=sys.argv[1:]
for b in ids:
    g=json.load(open(f'st/{b}.json'))['bar']
    rng={k:(round(min(v),1),round(max(v),1),len(set(round(x,2) for x in v))) for k,v in g.items()}
    print(b, rng)
    voc=g.get('voc')
    if not voc:
        print('FAIL', b, 'still no voc'); bad=1; continue
    v=np.array(voc,float)
    if len(set(np.round(v,2)))<=3 or float(v.max())<=-90:
        print('FAIL', b, 'voc still stand-in/flat'); bad=1
if bad: raise SystemExit(1)
print('vocfix ok', len(ids), 'tracks')
PY
