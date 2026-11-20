#!/usr/bin/env bash
# SLOWPAIR (2026-11-20) like-for-like cohort vs current rules.json, then docs (+ clips only if it matches or beats).
set -euo pipefail
cd /workspace/mixes
python3 -c 'import json;r=json.load(open("protrans/rules.json"));assert "SLOWPAIR" not in r, "rules.json must not enable SLOWPAIR"'
export SP_WORKERS="${SP_WORKERS:-1}"
python3 protrans/eval_slowpair.py
python3 -c 'import json;r=json.load(open("protrans/rules.json"));assert "SLOWPAIR" not in r, "rules.json must not enable SLOWPAIR after eval"'
