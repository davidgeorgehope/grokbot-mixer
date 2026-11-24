#!/bin/bash
# Driver for jobs/runjob.sh fresh-1123: isolated ingest, then one-shot eval.
set -euo pipefail
cd /workspace/mixes/protrans
export TALK_THREADS="${TALK_THREADS:-2}"
export WORKERS="${WORKERS:-2}"
python3 replica/fresh_1123.py
exec bash replica/fresh1123_work/run_fresh.sh
