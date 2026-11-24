#!/usr/bin/env bash
# gated search, round 2: r6 pool first, then one ban-aware re-search (pool only, --verify 0) if the pool is blocked.
# Waits for DJ-2's render-mix10-r6g so the two Mix 10 jobs never run at once.
set -u
while grep -q running /workspace/mixes/jobs/render-mix10-r6g.status 2>/dev/null; do sleep 60; done
cd /workspace/mixes/src2 && . ../mix10/env10.sh
export CRATE_FILE=/workspace/mixes/mix10/crate_r5.txt PAIR_TABLE=pair_table_10r6.json
export TABLE_K=40 DROPPEN=60 BOTHMIN=8 COVPEN=300 OUTPEN=300 FAMBAN=0 BW=200,800 DROP_FRAC=0.333 BADW_NEWONLY=1 WIN_TOPK=400 SOFT=0 NUDGE=nudge08_r9c.json
export PREV_PLANS=plan_mix07_r17.json,plan_mix08_r11c.json,plan_mix09_r5b.json FRESHPEN=120 REUSEPEN=150 PINW='{}'
export SEESAW_BANFILE=seesaw_ban_10.json BLEND_AUDIO_GATE=1 GATE_BANFILE=/workspace/mixes/src2/blend_gate_bans_mix10.json PYTHONUNBUFFERED=1
nice -n 15 python3 gated.py search --base plan_mix10_base.json --pool plan_mix10_r6.pool.json --out plan_mix10_gs.json \
  --exclude cb2sbJ-ii-I,3cOEsXf-ic0 --max-plans 3 --rounds 1 --gain 9.0 --jobs 2 \
  --search "--min 60 --max 68 --open-any --verify 0 --beam 400 --exclude cb2sbJ-ii-I,3cOEsXf-ic0"
echo "search rc=$?"
