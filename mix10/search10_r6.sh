#!/usr/bin/env bash
# Mix 10 r6 search: crate_r5 plus exclude Hayling (exposed mid-track breakdown failed E1).
# Same table as r5 (window scores unchanged; entry_cliff is a search-time veto).
# search10.sh preserves caller CRATE_FILE / PAIR_TABLE.
set -euo pipefail
export CRATE_FILE=/workspace/mixes/mix10/crate_r5.txt
export PAIR_TABLE=pair_table_10r6.json
export NPAR=${NPAR:-2}
cd /workspace/mixes
exec bash mix10/search10.sh plan_mix10_r6.json \
  --exclude 3cOEsXf-ic0 \
  --ban 'GSzweUBnRYM>B8diXfhUkjI,B8diXfhUkjI>EpHrodtTiK0,EpHrodtTiK0>GgG1Cd9zITE,EpHrodtTiK0>q_cZZY0BehE'
