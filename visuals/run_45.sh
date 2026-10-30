#!/bin/bash
# Sequential Mix 04 then Mix 05 visuals: analyze -> backdrops -> render -> ffprobe -> upload(public) -> backup -> cleanup
cd /workspace/mixes/visuals; PY=/workspace/mixes/visuals/venv/bin/python; P=/workspace/mixes/visuals_progress.md
note(){ echo "- $(date +%m-%d\ %H:%M) [run_45] $*" >> $P; }
for spec in "04 mix04 dj-mix-04-128k.mp3" "05 mix05n dj-mix-05-128k.mp3"; do
 set -- $spec; N=$1; K=$2; A=/workspace/mixes/$3; OUT=dj-mix-$N-visuals-1080p30.mp4; LINK=up$N.link
 [ -s $LINK ] && { note "mix$N already uploaded, skip"; continue; }
 NT=$(python3 -c "import json;print(len(json.load(open('code/${K}_tracks.json'))['tracks']))")
 [ -s code/${K}_analysis.json ] || $PY code/analyze_mix.py $A code/${K}_tracks.json code/${K}_analysis.json > an$N.log 2>&1 || { note "mix$N analyze FAILED"; exit 1; }
 [ -d tex_$K ] || $PY code/procedural_backdrops2.py $NT tex_$K >> an$N.log 2>&1
 if ! ffprobe -v error $OUT >/dev/null 2>&1 || ! grep -q done r$N.log 2>/dev/null; then
  note "mix$N render start ($NT tracks) -> visuals/$OUT, log r$N.log"
  $PY code/render_visuals2.py code/${K}_analysis.json $A $OUT --tex tex_$K > r$N.log 2>&1 || { note "mix$N render FAILED (see r$N.log)"; exit 1; }
 fi
 D=$(ffprobe -v error -show_entries format=duration -of csv=p=0 $OUT); S=$(ffprobe -v error -show_entries stream=codec_type -of csv=p=0 $OUT | sort -u | tr '\n' ' ')
 AD=$(ffprobe -v error -show_entries format=duration -of csv=p=0 $A)
 python3 -c "import sys;sys.exit(0 if abs($D-$AD)<2 else 1)" && [[ "$S" == *audio*video* ]] || { note "mix$N ffprobe FAILED dur=$D audio=$AD streams=$S"; exit 1; }
 note "mix$N render OK dur=$D streams=$S; uploading public"
 (cd /workspace/mixes/src && python3 yt_upload.py /workspace/mixes/visuals/$OUT --title "DJ Grok Bot – Mix $N | Liquid Drum & Bass" --description "$(cat /workspace/mixes/yt_desc_$N.txt)") > up$N.log 2>&1
 grep -o 'https://youtu.be/[A-Za-z0-9_-]*' up$N.log > $LINK || { note "mix$N upload FAILED (up$N.log)"; exit 1; }
 note "mix$N uploaded $(cat $LINK) dur=$D"
 echo "- DONE $(date +%Y-%m-%d\ %H:%M): Mix $N visuals public $(cat $LINK)" >> /workspace/mixes/DOCKET.md
 bash /workspace/backup_mixer_to_git.sh >> bk$N.log 2>&1 && note "mix$N backup ok" || note "mix$N backup FAILED (bk$N.log)"
 rm -rf $OUT tex_$K $A; note "mix$N cleaned mp4/tex/audio"
done
note "ALL DONE (04+05)"
