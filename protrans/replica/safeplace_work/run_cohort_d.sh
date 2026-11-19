#!/bin/bash
# 2026-11-19: held-out score of PLACE=safe d (== e on the cohort: the veto changed no pick) via PICKER_WIN, rules.json unchanged
cd /workspace/mixes || exit 1
PICKER_WIN=/workspace/mixes/protrans/replica/safeplace_work/win_d_cohort.json python3 protrans/eval_cohort.py sfdcoh1119 || exit 2
