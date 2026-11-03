#!/bin/bash
# full-mix v1plus render: 4 segments in parallel, then concat video + full 128k audio
cd /workspace/mixes/viz06v3
python3 -c "import json;[print(t,round(L,4)) for t,L in json.load(open('segs.json'))]" | xargs -P4 -n2 sh -c 'cd /workspace/mixes/src2; V=/workspace/mixes/viz06v3; [ -s $V/$0.mp4 ] || NUDGE=/nonexistent python3 staff_viz.py $V/$0.wav $V/$0.part.mp4 --v1plus --dur $1 > $V/$0.log 2>&1 && mv $V/$0.part.mp4 $V/$0.mp4'
for f in seg*.wav; do t=${f%.wav}; echo "file '$t.mp4'"; done > list.txt
ffmpeg -loglevel error -y -f concat -safe 0 -i list.txt -i /workspace/mixes/deliver/06-v3/dj-mix-06-v3-128k.mp3 -map 0:v -map 1:a -c:v copy -c:a aac -b:a 192k -shortest dj-mix-06-v3-staffviz-720p.mp4
echo VIZDONE $?
