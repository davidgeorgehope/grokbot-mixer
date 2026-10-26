#!/bin/bash
cd /workspace/mixes; A=src/eval/analyze_pro_set.py; W=pro_sets/wav
python3 $A $W/hospital_podcast393.wav --anchors 330,628,883,1191,1468,1738,2041,2291,2920,3166 > eval/logs/hp.log 2>&1
python3 $A $W/dimension_allstars360.wav > eval/logs/dim.log 2>&1
python3 $A $W/wilkinson_oldguard.wav > eval/logs/og.log 2>&1
echo RESTDONE
