#!/bin/bash
# 2026-11-19 STRUCTW ablation / OUTRO_QC / SLOWDOWN: which pairs' engine family windows change per arm
cd /workspace/mixes/protrans/replica || exit 1
unset GATE_FEAT GATE_FLIB PICKER_WIN ONLY BAR_RESYNC THINDEF
export TD_TAG=struct TD_CFG='{"base":{},"B0":{"STRUCTB":"0"},"B100":{"STRUCTB":"100"},"QC":{"OUTRO_QC":"1"},"COND":{"STRUCT_COND":"1"},"SLOW":{"SLOWDOWN":"1"},"QCS":{"OUTRO_QC":"1","SLOWDOWN":"1"},"SLOWB":{"SLOWDOWN":"1","THIN_DROPCUE":"1"}}'
python3 thin_detect_1119.py
