#!/usr/bin/env bash
# r11: continue Mix 08 repair from the r10bb render. Rewindow is now allowed for bassgap/swapdip/N1
# (X1 still caps the bass handoff at crossfader x 0.2-0.65, so a mid-blend swap into an intro-until-drop
# window is fixed by a different window, not by loosening tests). Crate is crate_r11 (r10 plus Just Hold On
# original and three new official UKF/Liquicity tracks). Lilies kept. Tests untouched.
unset PSKILL PSDBG
export STRUCT=1 FADE=tail LOOP32=0 ECHO_MAX=2 PREF_W=0 SWAP_PHRASE=1 HIGH_SWAP=1 BASS_SWAP_BARS=2
cd /workspace/mixes/src2
python3 -u repair.py --plan plan_mix08_r10bb.json --out plan_mix08_r11.json --render mix08_r10bb \
  --history mix08_r9:../jobs/render-mix08-r9b.log,mix08_r9c:../jobs/render-mix08-r9c.log,mix08_r10x,mix08_r10,mix08_r10b,mix08_r10bb \
  --table pair_table_08.json --crate ../mix08/crate_r11.txt --tag mix08r11_ --budget-s 4000 --max-dry 400 \
  --rounds 3 --render-name mix08_r11 --gain 9.3 --nudge nudge08_r9c.json
