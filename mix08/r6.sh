#!/usr/bin/env bash
# r6: 46-track crate, added official already-prepped 4B/9B fills:
#   Maduk & Dennis Pedersen – Miles Apart (UKF, 4B)
#   London Elektricity – Meteorites (Danny Byrd Remix) (Hospital, 9B)
#   Wilkinson – Afterglow (VEVO, 9B)
# Same targets as r5: SOFT=0, DROP_FRAC=1/3, PINW kept, no --require.
unset PSKILL PSDBG
cd /workspace/mixes/src2
SOFT=0 DROP_FRAC=0.333 bash ../mix08/search.sh plan_mix08_r6.json
