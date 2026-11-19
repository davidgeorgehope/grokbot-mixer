#!/bin/bash
# DROPCAND research variants (flag only; rules.json untouched). Own checkpoint files gate_ckpt/dropx.jsonl, dropc.jsonl.
cd /workspace/mixes/protrans || exit 1
export LAZY=1 WORKERS=${WORKERS:-3}
python3 replica/eval_gate.py 'dropx={"DROPCAND": "exit"}' 'dropc={"DROPCAND": "cue"}'
