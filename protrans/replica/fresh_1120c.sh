#!/bin/bash
# fresh-1120c: resume the isolated Sirenity ofcHup56lME ingest, then run the
# promotion "zero new hard fails" eval. nightly_1120_wrap.py / nightly-n1120
# does not wait for or read this job. The n1120 promotion check consumes the
# result via replica/fresh1120_work/run_fresh.sh -> replica/fresh1120_eval.json
# (fresh_mixes.json spent flag). Compare that file to
# protrans/results/hill_climb_n1120.json after this job finishes.
set -euo pipefail
cd /workspace/mixes/protrans
export TALK_THREADS="${TALK_THREADS:-4}"
python3 replica/fresh_1120.py
exec bash replica/fresh1120_work/run_fresh.sh
