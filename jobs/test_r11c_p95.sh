#!/usr/bin/env bash
# Re-run guardrails + full pytest on the existing mix08_r11c render after the 2026-11-10 pro-p95
# calibration. Does not re-render and does not delete wavs.
# NUDGE must be exported: the beat-alignment test reads os.environ['NUDGE'] (default nudge.json,
# which is absent) and will flag the existing warp nudges as 11-13 ms drift if it is unset.
set -uo pipefail
export STRUCT=1 FADE=tail LOOP32=0 ECHO_MAX=2 PREF_W=0 SWAP_PHRASE=1 HIGH_SWAP=1 BASS_SWAP_BARS=2
export NUDGE=nudge08_r9c.json
NAME=mix08_r11c
MP3=/workspace/mixes/src2/mix08_r11c.mp3
cd /workspace/mixes/src2
for f in "${NAME}_meta.json" "${NAME}_raw.wav" "${NAME}_master.wav" "$MP3" "$NUDGE"; do
  [ -f "$f" ] || { echo "missing $f"; exit 2; }
done
# Guardrails already written this afternoon with N1_db=3.83 and n_fail=0; re-run to keep the json in lockstep.
python3 ../src/guardrails.py --name "$NAME" --mp3 "$MP3" --nudge "$NUDGE" --png 2>&1 | grep -vE "Warning|m=np"; G=${PIPESTATUS[0]}
mkdir -p "guard_${NAME}"
MIX_NAME="$NAME" MIX_MP3="$MP3" MIX_WAV="/workspace/mixes/src2/${NAME}_master.wav" python3 -m pytest -q -p no:cacheprovider ../src/tests ../src/build_qa > "guard_${NAME}/pytest.log" 2>&1
P=$?
tail -40 "guard_${NAME}/pytest.log"
python3 cue_report.py "${NAME}_meta.json" --json "guard_${NAME}/pro_likeness.json" || true
echo "RESULT guardrails_exit=$G pytest_exit=$P (no re-render, NUDGE=$NUDGE)"
[ "$G" = 0 ] && [ "$P" = 0 ]
