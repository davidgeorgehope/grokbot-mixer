#!/usr/bin/env bash
# The one render + test entry point for the crossfader engine.
# usage: bash src/render_and_test.sh <plan.json> <name> <out.mp3> <gain_dB> [nudge.json]
#   e.g. bash src/render_and_test.sh plan_60f.json mixS /workspace/mixes/dj-mix-03-60.mp3 9.0 nudge60f.json
# Runs in src2/: mix_simple.py -> <name>_raw.wav + <name>_meta.json; master.sh -> <name>_master.wav + 320k MP3 (prints LUFS/peak);
# guardrails.py -> guard_<name>/guardrails.json (+PNG per blend); pytest src/tests; cue_report.py pro-likeness (report only). Exit 0 only if guardrails AND tests pass.
set -uo pipefail
PLAN=$1; NAME=$2; MP3=$3; GAIN=$4; export NUDGE=${5:-${NUDGE:-nudge60f.json}}
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT/src2"
python3 restore_audio.py >/dev/null || exit 1  # stems/decodes are cleaned after each build; regenerate bit-exact from sources
python3 mix_simple.py --plan "$PLAN" --out "$NAME" 2>&1 | grep -v '^choose' || exit 1
bash ../src/master.sh "${NAME}_raw.wav" "$MP3" "$GAIN" "${NAME}_master.wav" || exit 1
python3 ../src/guardrails.py --name "$NAME" --mp3 "$MP3" --nudge "$NUDGE" --png 2>&1 | grep -vE "Warning|m=np"; G=${PIPESTATUS[0]}
MIX_NAME="$NAME" MIX_MP3="$MP3" MIX_WAV="$ROOT/src2/${NAME}_master.wav" python3 -m pytest -q -p no:cacheprovider ../src/tests 2>&1 | tail -15; P=${PIPESTATUS[0]}
python3 cue_report.py "${NAME}_meta.json" --json "guard_${NAME}/pro_likeness.json" || true  # report only, never gates
echo "RESULT guardrails_exit=$G pytest_exit=$P"
[ "${AUTO_CLEAN:-1}" = 1 ] && bash ../src/cleanup_after_build.sh  # stems, decodes, raw/master wavs; the MP3 deliverable stays
[ "$G" = 0 ] && [ "$P" = 0 ]
