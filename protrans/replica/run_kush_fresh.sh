#!/bin/bash
# fresh test 2 renders: KushSessions #303 only (John B Night Drive is spent). Own checkpoint names kush_*. Scored once afterwards.
cd /workspace/mixes/protrans || exit 1
export ONLY=kushsessions_yaWXrFBRYrM WORKERS=2
python3 replica/eval_gate.py 'kush_default={}' && LAZY=0 python3 replica/eval_gate.py 'kush_gated={"REPLICA": "gated"}' 'kush_on={"REPLICA": 1}' 'kush_dropx={"DROPCAND": "exit"}' 'kush_dropc={"DROPCAND": "cue"}'
