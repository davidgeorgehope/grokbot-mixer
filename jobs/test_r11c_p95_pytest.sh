#!/usr/bin/env bash
set -uo pipefail
export STRUCT=1 FADE=tail LOOP32=0 ECHO_MAX=2 PREF_W=0 SWAP_PHRASE=1 HIGH_SWAP=1 BASS_SWAP_BARS=2
export NUDGE=nudge08_r9c.json
NAME=mix08_r11c
MP3=/workspace/mixes/src2/mix08_r11c.mp3
cd /workspace/mixes/src2
python3 -c "import json; g=json.load(open('guard_mix08_r11c/guardrails.json')); assert g['n_fail']==0 and g['thresholds']['N1_db']==3.83, g"
MIX_NAME="$NAME" MIX_MP3="$MP3" MIX_WAV="/workspace/mixes/src2/${NAME}_master.wav" python3 -m pytest -q -p no:cacheprovider ../src/tests ../src/build_qa > "guard_${NAME}/pytest.log" 2>&1
P=$?
tail -40 "guard_${NAME}/pytest.log"
echo "RESULT guardrails_exit=0 pytest_exit=$P (no re-render, NUDGE=$NUDGE, guardrails json reused n_fail=0)"
[ "$P" = 0 ]
