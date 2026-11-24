#!/usr/bin/env bash
# Mix 10 round 5: crate_r5 = crate_r2 minus Cloudwater and Miles Apart.
# Saviour / Tear Drops stay out (no 16-bar beat-on-beat entry). Uses a new
# pair table so table_key's voc feature signature is baked in.
# Same test limits as r1–r4. --ban values MUST be quoted.
set -euo pipefail
cd /workspace/mixes/src2
export CRATE_FILE=/workspace/mixes/mix10/crate_r5.txt
export PAIR_TABLE=pair_table_10r5.json
export NPAR=${NPAR:-2}
exec bash /workspace/mixes/mix10/search10.sh plan_mix10_r5.json \
  --exclude B8diXfhUkjI,EpHrodtTiK0,pUUrJH7jzAQ,ujjImKRMX-M \
  --ban 'GSzweUBnRYM>B8diXfhUkjI,B8diXfhUkjI>EpHrodtTiK0,EpHrodtTiK0>GgG1Cd9zITE,EpHrodtTiK0>q_cZZY0BehE'
