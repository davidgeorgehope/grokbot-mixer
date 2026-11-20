#!/usr/bin/env bash
# SLOWPAIR exit-only (2026-11-20): Case A only, on the current default and on epg_stack.
# Never writes rules.json.
set -euo pipefail
cd /workspace/mixes
python3 -c 'import json;r=json.load(open("protrans/rules.json"));
assert "SLOWPAIR" not in r and "SLOWPAIR_EXIT" not in r, "rules.json must not enable SLOWPAIR"'
export SP_WORKERS="${SP_WORKERS:-1}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
python3 protrans/eval_slowpair_exit.py
python3 -c 'import json;r=json.load(open("protrans/rules.json"));
assert "SLOWPAIR" not in r and "SLOWPAIR_EXIT" not in r, "rules.json must not enable SLOWPAIR after eval"'
