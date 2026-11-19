#!/bin/bash
# 2026-11-19 wrap-up: real engine default on the fresh mix (fdef1119), sources from replica/fresh_work/lib
cd /workspace/mixes/protrans || exit 1
export EXTRA_SRC=/workspace/mixes/protrans/replica/fresh_work/lib
ONLY=offbeatdooter_L0O51m1Ow7I WORKERS=3 python3 replica/eval_gate.py 'fdef1119={}'
