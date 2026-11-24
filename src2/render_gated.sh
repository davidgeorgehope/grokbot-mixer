#!/usr/bin/env bash
# Gated render (BLEND_AUDIO_GATE, RCA 2026-11-24): same steps as mix10/render10.sh (restore, mix_simple, master, guardrails, pytest,
# cue report) with two changes, thresholds untouched:
#   1. before rendering: gated.py check (dry gates + every blend's own audio + solo breakdown holes) must pass;
#   2. the master gain is chosen by gain_step.py (full master per 0.5 dB step from START_GAIN until true peak <= -1.0 dBTP),
#      so guardrails + pytest run once, on a master that already passes P1.
# usage: render_gated.sh <plan.json> <name> <out.mp3> <start_gain> [nudge.json]   (source the mix env first)
set -uo pipefail
PLAN=$1; NAME=$2; MP3=$3; GAIN=$4; export NUDGE=${5:-${NUDGE:-nudge08_r9c.json}}
cd /workspace/mixes/src2
python3 gated.py check --plan "$PLAN" --gain "$GAIN" --jobs "${GATE_JOBS:-3}" || { echo "GATE FAILED: not rendering"; exit 4; }
python3 restore_audio.py $(python3 -c "import json,sys;print(' '.join(p['id'] for p in json.load(open(sys.argv[1]))))" "$PLAN") >/dev/null || exit 1
python3 mix_simple.py --plan "$PLAN" --out "$NAME" 2>&1 | grep -v '^choose'; R=${PIPESTATUS[0]}; [ "$R" = 0 ] || { echo "mix_simple rc=$R"; exit 1; }
python3 gain_step.py "${NAME}_raw.wav" --start "$GAIN" --out-mp3 "$MP3" --out-master "${NAME}_master.wav" --json "${NAME}_gain.json" || { echo "GAIN STEP: no gain >= floor passes true peak"; exit 5; }
python3 cleanup_round_wavs.py "$NAME" || true
python3 ../src/guardrails.py --name "$NAME" --mp3 "$MP3" --nudge "$NUDGE" --png 2>&1 | grep -vE "Warning|m=np"; G=${PIPESTATUS[0]}
mkdir -p "guard_${NAME}"; MIX_NAME="$NAME" MIX_MP3="$MP3" MIX_WAV="/workspace/mixes/src2/${NAME}_master.wav" python3 -m pytest -q -p no:cacheprovider ../src/tests ../src/build_qa > "guard_${NAME}/pytest.log" 2>&1; P=$?; tail -25 "guard_${NAME}/pytest.log"
python3 cue_report.py "${NAME}_meta.json" --json "guard_${NAME}/pro_likeness.json" || true
echo "RESULT gain=$(python3 -c "import json;print(json.load(open('${NAME}_gain.json'))['gain'])") guardrails_exit=$G pytest_exit=$P"
[ "$G" = 0 ] && [ "$P" = 0 ]
