#!/usr/bin/env bash
# r10: DJustify-style auto-repair of r9c. Culprits = r9c render failures (guardrails + pytest log); repair.py swaps or inserts
# an incoming crate track per failing blend, re-picks windows, dry-checks every candidate. Tests untouched.
unset PSKILL PSDBG
export STRUCT=1 FADE=tail LOOP32=0 ECHO_MAX=2 PREF_W=0 SWAP_PHRASE=1 HIGH_SWAP=1 BASS_SWAP_BARS=2
cd /workspace/mixes/src2
python3 -u repair.py --plan plan_mix08_r9c.json --out plan_mix08_r10.json --render mix08_r9c --log ../jobs/render-mix08-r9c.log --history mix08_r9:../jobs/render-mix08-r9b.log \
  --table pair_table_08.json --crate ../mix08/crate.txt --tag mix08r10_ --budget-s 3000 --max-dry 250
