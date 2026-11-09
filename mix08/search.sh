#!/usr/bin/env bash
# Mix 08 planner run (open order over the 30-track crate). usage: search.sh OUT LOG [extra args]
cd /workspace/mixes/src2
export STRUCT=1 FADE=tail LOOP32=0 ECHO_MAX=2 PREF_W=0 PREFW=0 SWAP_PHRASE=1 HIGH_SWAP=1 BASS_SWAP_BARS=2
export PAIR_TABLE=pair_table_08.json TABLE_K=40 DROPPEN=60 BOTHMIN=8 COVPEN=300 OUTPEN=300 FAMBAN=0 BW=${BW:-200,800} DROP_FRAC=${DROP_FRAC:-0.3} BADW_NEWONLY=1 WIN_TOPK=400 SOFT=${SOFT:-0} NUDGE=nudge05n.json
export PREV_PLANS=plan_mix07_r17.json
export PINW=${PINW:-'{"j9AuFRpLk7U>cxS6yd0UAxw":["lb",176,null,48,32]}'}
OUT=$1; shift
python3 plan_search.py search --base plan_mix08_base.json --out "$OUT" --min 60 --max 68 --open-any --verify ${VERIFY:-40} --beam ${BEAM:-400} "$@"
