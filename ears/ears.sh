#!/usr/bin/env bash
# Per-blend ears check for a render meta. Box: cut decks (light). GPU host: stems + Beat This + Basic Pitch.
# Usage: EARS_HOST=<ssh alias> bash ears/ears.sh src2/<prefix>_meta.json [nudge.json] > report path printed
set -euo pipefail
META=$(realpath "$1"); NUDGE=${2:+--nudge $(realpath "$2")}; H=${EARS_HOST:?set EARS_HOST to the GPU host ssh alias}
D=$(realpath "$(dirname "$0")"); NAME=$(basename "$META" _meta.json); TMP=$(mktemp -d /tmp/ears_XXXX); trap 'rm -rf "$TMP"' EXIT
# Probe first so a down/wrong host exits 1 with a message instead of ssh's 255 after a partial copy.
if ! ssh -o BatchMode=yes -o ConnectTimeout=8 "$H" "test -d ~/ears && test -x ~/ears/.venv/bin/python" >/dev/null 2>&1; then
  echo "ears.sh: GPU host '$H' unreachable or missing ~/ears (not the iCloud HOST). Set EARS_HOST to the GPU alias." >&2
  exit 1
fi
(cd "$D/../src2" && python3 "$D/ears_cut.py" "$META" "$TMP/$NAME" $NUDGE)
scp -q -o BatchMode=yes -o ConnectTimeout=8 "$D/ears_check.py" "$H:ears/" || { echo "ears.sh: scp to $H failed" >&2; exit 1; }
tar -C "$TMP" -cf - "$NAME" | ssh -o BatchMode=yes -o ConnectTimeout=8 "$H" "tar -C ~/ears -xf -" || { echo "ears.sh: upload to $H failed" >&2; exit 1; }
ssh -o BatchMode=yes -o ConnectTimeout=8 "$H" "cd ~/ears && .venv/bin/python ears_check.py $NAME --out $NAME.report.json >/dev/null 2>&1; cat $NAME.report.json; rm -rf $NAME $NAME.report.json" > "$D/${NAME}_ears_report.json"   || { echo "ears.sh: remote ears_check on $H failed" >&2; exit 1; }
python3 -c "import json,sys;R=json.load(open(sys.argv[1]));[m.pop('bt',None) for m in R['blends']];json.dump(R,open(sys.argv[1],'w'),indent=1);[print('%2d %5.0fs %s'%(m['k'],m['t0'],m['verdict'])) for m in R['blends']]" "$D/${NAME}_ears_report.json"
echo "$D/${NAME}_ears_report.json"
