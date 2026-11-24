#!/usr/bin/env bash
# after blendgate-validate-v2: cross-check flagged "clean" blends on the full mix, then the gated search smoke (no render)
set -u
while grep -q running /workspace/mixes/jobs/blendgate-validate-v2.status; do sleep 30; done
cd /workspace/mixes/src2 && . ../mix10/env10.sh
export NUDGE=nudge08_r9c.json PYTHONUNBUFFERED=1
echo "=== crosscheck ==="
nice -n 15 python3 blend_gate_crosscheck.py ../eval/blend_gate_validation_mix10.json ../eval/blend_gate_validation_holdout.json
export CRATE_FILE=/workspace/mixes/mix10/crate_r5.txt PAIR_TABLE=pair_table_10r6.json BLEND_AUDIO_GATE=1 GATE_BANFILE=/workspace/mixes/src2/blend_gate_bans_mix10.json
echo "=== gated search smoke: r6 pool, no Memory Lane / Hayling, up to 3 plans ==="
nice -n 15 python3 gated.py search --base plan_mix10_base.json --pool plan_mix10_r6.pool.json --out plan_mix10_gs.json --exclude cb2sbJ-ii-I,3cOEsXf-ic0 --max-plans 3 --rounds 0 --gain 9.0 --jobs 2
echo "search rc=$?"
rm -rf blend_gate_clips/*
