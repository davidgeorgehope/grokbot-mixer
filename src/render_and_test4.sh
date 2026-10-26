#!/bin/bash
# usage: render_and_test4.sh PLAN NAME OUT_MP3 GAIN — render, master, guardrails (fail-hard), QA tests; non-zero exit = failed build
set -e;cd /workspace/mixes/src2
NUDGE=${NUDGE:-nudge60.json} python3 mix3.py --plan $1 --out $2
bash ../src/master.sh $2_raw.wav $3 $4
set +e
python3 ../src/guardrails.py --name $2 --mp3 $3 --nudge ${NUDGE:-nudge60.json} --png;G=$?
MIX_NAME=$2 MIX_MP3=$3 NUDGE=${NUDGE:-nudge60.json} python3 -m pytest -q /workspace/mixes/src/tests;Q=$?
echo "GUARDRAILS_EXIT=$G TESTS_EXIT=$Q";exit $((G|Q))
