#!/usr/bin/env bash
# BASS_FILL (2026-11-20) like-for-like cohort: current rules.json vs rules + BASS_FILL=1, then blend diagnostics + must-pass.
set -euo pipefail
cd /workspace/mixes
python3 protrans/eval_bass_fill.py bfb1120_base
python3 protrans/eval_bass_fill.py bff1120_fill bassfill
python3 protrans/eval_tailexit.py bfb1120_base bff1120_fill
