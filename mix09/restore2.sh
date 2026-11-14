#!/usr/bin/env bash
cd /workspace/mixes/src2 && cat ../mix09/crate.txt | tr ' ' '\n' | grep . | xargs -P4 -n1 python3 restore_audio.py && \
FRESHPEN=120 REUSEPEN=150 bash ../mix09/search09.sh plan_mix09_r2.json
