#!/bin/bash
# waits for run.sh, gates sync <=40 ms per segment and duration, then public YouTube upload + oembed check + backup
cd /workspace/mixes/viz06v3
while ! grep -q VIZDONE run.log; do sleep 60; done
grep -q "VIZDONE 0" run.log || { echo "ABORT render failed"; exit 1; }
for f in seg*.log; do o=$(grep -o "sync offset[^:]*: [-+0-9]* ms" $f | grep -o "[-+][0-9]*" | tail -1); echo "$f $o"; [ -n "$o" ] && [ ${o#[-+]} -le 40 ] || { echo "ABORT sync $f $o"; exit 1; }; done
V=dj-mix-06-v3-staffviz-720p.mp4;dv=$(ffprobe -v error -show_entries format=duration -of csv=p=0 $V);da=$(ffprobe -v error -show_entries format=duration -of csv=p=0 /workspace/mixes/deliver/06-v3/dj-mix-06-v3-128k.mp3);echo dur $dv $da
python3 -c "import sys;sys.exit(abs($dv-$da)>2)" || { echo "ABORT duration"; exit 1; }
D=/workspace/mixes/deliver/06-v3
cd /workspace/mixes/src && python3 yt_upload.py /workspace/mixes/viz06v3/$V --title 'DJ Grok Bot – Mix 06 v3 | Liquid Drum & Bass' --description "$(cat $D/yt_desc.txt)" --privacy public > $D/yt_upload.log 2>&1
L=$(grep -o "https://youtu.be/[A-Za-z0-9_-]*" $D/yt_upload.log | tail -1); [ -n "$L" ] || { echo "ABORT upload"; exit 1; }
echo $L > $D/youtube.link; echo "LINK $L"
curl -s "https://www.youtube.com/oembed?url=$L&format=json" | tee $D/oembed.json; echo
echo "- $(date +%H:%M) ET: [deliver 06-v3] YouTube public $L (staff_viz v1plus 720p)" >> /workspace/mixes/PROGRESS_mix06.md
bash /workspace/backup_mixer_to_git.sh; echo AFTERDONE
