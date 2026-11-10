#!/usr/bin/env bash
# r10b: continue the r10 repair loop from plan_mix08_r10.json using the mix08_r10 render's failures (guardrails + full pytest log).
# Earlier culprit pairs stay banned (--culprit), earlier render-failed windows never re-picked (--history). Tests untouched.
unset PSKILL PSDBG
export STRUCT=1 FADE=tail LOOP32=0 ECHO_MAX=2 PREF_W=0 SWAP_PHRASE=1 HIGH_SWAP=1 BASS_SWAP_BARS=2
cd /workspace/mixes/src2
python3 -u repair.py --plan plan_mix08_r10.json --out plan_mix08_r10b.json --render mix08_r10 \
  --history mix08_r9:../jobs/render-mix08-r9b.log,mix08_r9c:../jobs/render-mix08-r9c.log,mix08_r10x \
  --culprit "N-j7tIeGm1E>nT25guf4DRU:L1,LJJ4cJzpjKk>EiZVTuiqo0w:G1,q_IuTV23x7Q>5gFutO20uKA:tail,1q43f05ChUs>nT25guf4DRU:E1" \
  --table pair_table_08.json --crate ../mix08/crate_r10.txt --tag mix08r10b_ --budget-s 4000 --max-dry 400 \
  --rounds 3 --render-name mix08_r10b --gain 9.3 --nudge nudge08_r9c.json
