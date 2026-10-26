#!/bin/bash
# Re-runs every set analysis. Anchors = published YouTube chapter timestamps (pro sets) or tracklist times (our mixes).
cd /workspace/mixes
export OMP_NUM_THREADS=3 MKL_NUM_THREADS=3
A=src/eval/analyze_pro_set.py; W=pro_sets/wav
python3 $A $W/wilkinson_boomtown2026.wav --anchors 388,410,650,800,910,1019,1170,1288,1698,1935,2140,2423,2644,2795,3126,3280,3365,3712,3865,3967,4186 > eval/logs/wb.log 2>&1 &
python3 $A $W/hospital_podcast393.wav --anchors 330,628,883,1191,1468,1738,2041,2291,2920,3166 > eval/logs/hp.log 2>&1 &
python3 $A $W/dimension_allstars360.wav > eval/logs/dim.log 2>&1 &
wait
python3 $A $W/wilkinson_oldguard.wav > eval/logs/og.log 2>&1 &
python3 $A $W/dj-mix-01.wav --anchors 199,386,695,927,1104,1313 > eval/logs/m1.log 2>&1 &
python3 $A $W/dj-mix-02.wav --anchors 219,387,515,697,808,990,1179,1335,1470,1736,1913,2023 > eval/logs/m2.log 2>&1 &
wait
echo ALLDONE
