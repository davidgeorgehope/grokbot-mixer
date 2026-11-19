#!/bin/bash
# 2026-11-19 EXITPOS: which pairs' engine family windows change (alone / + SLOWDOWN)
cd /workspace/mixes/protrans/replica || exit 1
unset GATE_FEAT GATE_FLIB PICKER_WIN ONLY BAR_RESYNC THINDEF
export TD_TAG=ep TD_POOL=3 TD_CFG='{"base":{},"EP":{"EXITPOS":"1"},"EPS":{"EXITPOS":"1","SLOWDOWN":"1"}}'
python3 thin_detect_1119.py
