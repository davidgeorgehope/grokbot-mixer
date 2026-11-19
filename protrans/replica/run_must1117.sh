#!/bin/bash
# must-catch clash: joe_syntax_hospital__11 as the listener heard it on 2026-11-17 (before BLEND_LOCK). Own checkpoint must1117_*.
cd /workspace/mixes/protrans || exit 1
ONLY=joe_syntax_hospital__11 WORKERS=1 python3 replica/eval_gate.py 'must1117_nolock={"BLEND_LOCK": 0}'
