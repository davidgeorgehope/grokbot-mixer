#!/usr/bin/env bash
# Per-blend ears check for a render meta. Box: cut decks (light). GPU host: stems + Beat This + Basic Pitch.
# Usage: EARS_HOST=<ssh alias> bash ears/ears.sh src2/<prefix>_meta.json [nudge.json] > report path printed
set -euo pipefail
META=$(realpath "$1"); NUDGE=${2:+--nudge $(realpath "$2")}; H=${EARS_HOST:?set EARS_HOST to the GPU host ssh alias}
D=$(realpath "$(dirname "$0")"); NAME=$(basename "$META" _meta.json); TMP=$(mktemp -d /tmp/ears_XXXX); trap 'rm -rf "$TMP"' EXIT
(cd "$D/../src2" && python3 "$D/ears_cut.py" "$META" "$TMP/$NAME" $NUDGE)
scp -q "$D/ears_check.py" "$H:ears/"; tar -C "$TMP" -cf - "$NAME" | ssh -o BatchMode=yes "$H" "tar -C ~/ears -xf -"
ssh -o BatchMode=yes "$H" "cd ~/ears && .venv/bin/python ears_check.py $NAME --out $NAME.report.json >/dev/null 2>&1; cat $NAME.report.json; rm -rf $NAME $NAME.report.json" > "$D/${NAME}_ears_report.json"
python3 -c "import json,sys;R=json.load(open(sys.argv[1]));[m.pop('bt',None) for m in R['blends']];json.dump(R,open(sys.argv[1],'w'),indent=1);[print('%2d %5.0fs %s'%(m['k'],m['t0'],m['verdict'])) for m in R['blends']]" "$D/${NAME}_ears_report.json"
echo "$D/${NAME}_ears_report.json"
