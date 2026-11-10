#!/usr/bin/env bash
# r10: DJustify-style auto-repair of r9c with render feedback. Culprits = r9c render failures (guardrails + pytest log).
# repair.py swaps/inserts an incoming (or outgoing) crate track per failing blend, or a clearly different window for a
# phase-slip/abrupt-tail fail, dry-checks every candidate, renders only when every culprit is cleared; a render fail
# feeds its own culprits into the next round (max 3 renders). Tests untouched.
unset PSKILL PSDBG
export STRUCT=1 FADE=tail LOOP32=0 ECHO_MAX=2 PREF_W=0 SWAP_PHRASE=1 HIGH_SWAP=1 BASS_SWAP_BARS=2
cd /workspace/mixes/src2
python3 -u repair.py --plan plan_mix08_r9c.json --out plan_mix08_r10.json --render mix08_r9c --log ../jobs/render-mix08-r9c.log --history mix08_r9:../jobs/render-mix08-r9b.log,mix08_r10x --culprit "1q43f05ChUs>nT25guf4DRU:E1" \
  --table pair_table_08.json --crate ../mix08/crate_r10.txt --tag mix08r10_ --budget-s 3000 --max-dry 250 \
  --rounds 3 --render-name mix08_r10 --gain 9.3 --nudge nudge08_r9c.json
