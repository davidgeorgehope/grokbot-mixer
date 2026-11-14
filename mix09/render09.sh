#!/usr/bin/env bash
# Mix 09 wrapper = mix08/render08.sh (same steps: restore plan tracks, mix_simple, master, guardrails, pytest, cue report) with the Mix 09 env.
# usage: render09.sh <plan.json> <name> <out.mp3> <gain_dB> [nudge.json]
set -uo pipefail
. /workspace/mixes/mix09/env09.sh
PLAN=$1; NAME=$2; MP3=$3; GAIN=$4; export NUDGE=${5:-${NUDGE:-nudge08_r9c.json}}
cd /workspace/mixes/src2
python3 restore_audio.py $(python3 -c "import json,sys;print(' '.join(p['id'] for p in json.load(open(sys.argv[1]))))" "$PLAN") >/dev/null || exit 1
python3 mix_simple.py --plan "$PLAN" --out "$NAME" 2>&1 | grep -v '^choose'; R=${PIPESTATUS[0]}; [ "$R" = 0 ] || { echo "mix_simple rc=$R"; exit 1; }
bash ../src/master.sh "${NAME}_raw.wav" "$MP3" "$GAIN" "${NAME}_master.wav" || exit 1
python3 cleanup_round_wavs.py "$NAME" || true
python3 ../src/guardrails.py --name "$NAME" --mp3 "$MP3" --nudge "$NUDGE" --png 2>&1 | grep -vE "Warning|m=np"; G=${PIPESTATUS[0]}
mkdir -p "guard_${NAME}"; MIX_NAME="$NAME" MIX_MP3="$MP3" MIX_WAV="/workspace/mixes/src2/${NAME}_master.wav" python3 -m pytest -q -p no:cacheprovider ../src/tests ../src/build_qa > "guard_${NAME}/pytest.log" 2>&1; P=$?; tail -25 "guard_${NAME}/pytest.log"
python3 cue_report.py "${NAME}_meta.json" --json "guard_${NAME}/pro_likeness.json" || true
echo "RESULT guardrails_exit=$G pytest_exit=$P"
[ "$G" = 0 ] && [ "$P" = 0 ]
