#!/usr/bin/env bash
cd /workspace/mixes/src2 && . ../mix10/env10.sh && export NUDGE=nudge08_r9c.json PYTHONUNBUFFERED=1 && nice -n 15 python3 blend_gate_validate.py 2 && nice -n 15 python3 blend_gate_validate.py 2 holdout
