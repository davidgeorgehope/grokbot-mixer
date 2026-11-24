#!/usr/bin/env bash
# Mix 10 round 4: reuse pair_table_10r3 / crate_r2, but drop Cloudwater and Miles Apart
# (they sat in every r3 feasible plan and failed dry drums_only + vocal). Same test limits.
# --ban values MUST be quoted: '>' is a shell redirect.
set -euo pipefail
cd /workspace/mixes/src2
. ../mix10/env10.sh
export CRATE_FILE=/workspace/mixes/mix10/crate_r2.txt
export PAIR_TABLE=pair_table_10r3.json
export NPAR=${NPAR:-2}
exec bash ../mix10/search10.sh plan_mix10_r4.json \
  --exclude B8diXfhUkjI,EpHrodtTiK0 \
  --ban 'GSzweUBnRYM>B8diXfhUkjI,B8diXfhUkjI>EpHrodtTiK0,EpHrodtTiK0>GgG1Cd9zITE,EpHrodtTiK0>q_cZZY0BehE'
