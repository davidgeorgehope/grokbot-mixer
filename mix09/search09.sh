#!/usr/bin/env bash
# Mix 09 planner run (open order over the pinned crate). usage: search09.sh OUT [extra args]
cd /workspace/mixes/src2; . ../mix09/env09.sh
export TABLE_K=40 DROPPEN=60 BOTHMIN=8 COVPEN=300 OUTPEN=300 FAMBAN=0 BW=${BW:-200,800} DROP_FRAC=${DROP_FRAC:-0.333} BADW_NEWONLY=1 WIN_TOPK=400 SOFT=${SOFT:-0} NUDGE=nudge08_r9c.json
export PREV_PLANS=plan_mix07_r17.json,plan_mix08_r11c.json FRESHPEN=${FRESHPEN:-40} REUSEPEN=${REUSEPEN:-30} PINW=${PINW:-'{}'} DRY_BUDGET_S=${DRY_BUDGET_S:-3600}
OUT=$1; shift
python3 -u plan_search.py search --base plan_mix09_base.json --out "$OUT" --min 60 --max 68 --open-any --verify ${VERIFY:-40} --beam ${BEAM:-400} "$@"
