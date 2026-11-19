#!/usr/bin/env bash
# re-render default rows that failed on the missing rubberband CLI (installed 2026-11-18 20:51 ET)
cd /workspace/mixes/protrans
WORKERS=2 python3 replica/eval_gate.py 'default={}'
