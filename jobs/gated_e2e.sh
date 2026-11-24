#!/usr/bin/env bash
# end-to-end smoke of the gate wiring on Mix 10 history (no render, no delivery)
cd /workspace/mixes/src2 && . ../mix10/env10.sh
export CRATE_FILE=/workspace/mixes/mix10/crate_r5.txt PAIR_TABLE=pair_table_10r6.json NUDGE=nudge08_r9c.json PYTHONUNBUFFERED=1 BLEND_AUDIO_GATE=1
export GATE_BANFILE=/workspace/mixes/src2/blend_gate_bans_mix10.json
echo "=== check plan_mix10_r6c.json (rendered r6c: expect dry OK, 6 blend fails) ==="
nice -n 15 python3 gated.py check --plan plan_mix10_r6c.json --gain 9.0 --jobs 2
echo "=== search over r6 pool, no Memory Lane / Hayling, 2 plans ==="
nice -n 15 python3 gated.py search --base plan_mix10_base.json --pool plan_mix10_r6.pool.json --out plan_mix10_gs.json --exclude cb2sbJ-ii-I,3cOEsXf-ic0 --max-plans 2 --rounds 0 --gain 9.0 --jobs 2
echo "search rc=$?"
