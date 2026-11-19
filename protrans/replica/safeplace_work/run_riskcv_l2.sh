#!/bin/bash
# 2026-11-19 RCA: risk-model CV with the LANES2 features (summed-lows drop + thin swap) vs c's features, same data
cd /workspace/mixes/protrans/replica || exit 1
export PUMPF=1 LANES=1 TAIL6=1 GAPX=1 SECPEN=0.1 EXTRA_RV=sp1119a1,sp1119a2,sp1119b1,sp1119b2,sp1119c1,sp1119c2,sp1119d1,sp1119d2
TAG=_c_more python3 safeplace_1119.py risk || exit 2
LANES2=1 TAG=_l2 python3 safeplace_1119.py risk || exit 3
