#!/usr/bin/env bash
cd /workspace/mixes/src2 && export PYTHONUNBUFFERED=1 && nice -n 15 python3 gain_step.py mix10_r6_raw.wav --start 9.0 --json ../eval/gain_step_validation_mix10_r6.json
