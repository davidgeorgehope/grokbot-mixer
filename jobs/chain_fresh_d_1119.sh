#!/bin/bash
# wait for fresh-1119t; if it found a fresh mix, run the one-shot variant d fresh validation through runjob (clean env)
cd /workspace/mixes
while grep -q running jobs/fresh-1119t.status; do sleep 30; done
if grep -q '^FRESH' jobs/fresh-1119t.log; then
  env -u GATE_FEAT -u GATE_FLIB -u EXTRA_SRC -u PICKER_WIN -u ONLY -u BAR_RESYNC jobs/runjob.sh fresh-d-1119t bash protrans/replica/safeplace_work/run_fresh_d.sh
else echo "no fresh mix found"; fi
