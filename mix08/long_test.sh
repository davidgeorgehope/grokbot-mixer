#!/usr/bin/env bash
# 2026-11-11 full-mix proof of FADE=long: Mix 08 v2 (r11c, https://youtu.be/jRTCAA4PpLY) plan and env unchanged except the
# four long-blend keys the listener approved for practice blends. Audio only: no video, no YouTube, no Drive.
# usage: long_test.sh [name]   (default mix08_long1)
set -uo pipefail
NAME=${1:-mix08_long1}; PLAN=plan_mix08_r11c.json; MP3=/workspace/mixes/src2/${NAME}.mp3
export STRUCT=1 FADE=long LONG_SOLO=16 LONG_SWAP=exit LONG_SOLO_STRUCT=1 LOOP32=0 ECHO_MAX=2 PREF_W=0 SWAP_PHRASE=1 HIGH_SWAP=1 HIGH_OFS=8 BASS_SWAP_BARS=4
export NUDGE=nudge08_long.json  # copy of r9c plus Me & You intro nudges for N1 at 13:42; do not edit r9c in place
cd /workspace/mixes/src2
python3 restore_audio.py $(python3 -c "import json,sys;print(' '.join(p['id'] for p in json.load(open(sys.argv[1]))))" "$PLAN") >/dev/null || exit 1
python3 mix_simple.py --plan "$PLAN" --out "$NAME" 2>&1 | grep -v '^choose'; R=${PIPESTATUS[0]}
echo "RENDER mix_simple_exit=$R"; [ "$R" = 0 ] || exit 1
bash ../src/master.sh "${NAME}_raw.wav" "$MP3" 9.3 "${NAME}_master.wav" || exit 1
python3 ../src/guardrails.py --name "$NAME" --mp3 "$MP3" --nudge "$NUDGE" --png 2>&1 | grep -vE "Warning|m=np"; G=${PIPESTATUS[0]}
mkdir -p "guard_${NAME}"; MIX_NAME="$NAME" MIX_MP3="$MP3" MIX_WAV="/workspace/mixes/src2/${NAME}_master.wav" nice python3 -m pytest -q -p no:cacheprovider -rf ../src/tests ../src/build_qa > "guard_${NAME}/pytest.log" 2>&1; P=$?; tail -40 "guard_${NAME}/pytest.log"
nice python3 blend_diag.py --meta "${NAME}_meta.json" --out ../deliver/${NAME}/diagnostics > "guard_${NAME}/blend_diag.log" 2>&1; D=$?
echo "RESULT guardrails_exit=$G pytest_exit=$P blend_diag_exit=$D"
[ "$G" = 0 ] && [ "$P" = 0 ]
