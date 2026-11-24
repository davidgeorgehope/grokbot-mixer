#!/bin/bash
# Ingest the two additional fresh mixes, then one-shot eval of all three.
set -euo pipefail
cd /workspace/mixes/protrans
export TALK_THREADS="${TALK_THREADS:-2}"
export WORKERS="${WORKERS:-2}"
python3 replica/fresh_1123_more.py
exec bash replica/fresh1123_work/run_fresh.sh
