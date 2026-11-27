#!/usr/bin/env bash
# n1127 renders: official hard checks + injected-fault detector rates on tonight's default cohort (lcb_1127, rendered 00:42 by the
# levelcomp research job = current ridegate default), then the two drum-clash landing-fade arms on top of the default with DCLASH counts.
cd /workspace/mixes; set -e; R=protrans/replica
nice -n 10 python3 $R/hc_1127.py lcb_1127
nice -n 10 python3 $R/hcinject_1127.py lcb_1127
WORKERS=3 nice -n 10 python3 $R/render_1127.py dclash_land6 n27d6
nice -n 10 python3 $R/hc_1127.py n1127_dclash_land6
WORKERS=3 nice -n 10 python3 $R/render_1127.py dclash_land7 n27d7
nice -n 10 python3 $R/hc_1127.py n1127_dclash_land7
echo ALLDONE $(date)
