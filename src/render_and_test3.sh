#!/bin/bash
# usage: render_and_test.sh PLAN NAME OUT_MP3 GAIN — render, master, run QA; non-zero exit = failed build
set -e;cd /workspace/mixes/src2
python3 mix3.py --plan $1 --out $2
bash ../src/master.sh $2_raw.wav $3 $4
MIX_NAME=$2 MIX_MP3=$3 python3 -m pytest -q /workspace/mixes/src/tests
