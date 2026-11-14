#!/usr/bin/env bash
set -euo pipefail
cd /workspace/mixes/deliver/09
ffmpeg -loglevel error -y -i ../../src2/mix09_r5b_master.wav -c:a libmp3lame -b:a 128k dj-mix-09-128k.mp3
ffprobe -v error -show_entries format=duration -of csv=p=0 dj-mix-09-128k.mp3
R=~/bin/rclone; NAME="DJ Grok Bot – Mix 09"
$R copyto dj-mix-09-128k.mp3 "gdrive:$NAME"
$R lsl "gdrive:" --include "$NAME" --max-depth 1
$R link "gdrive:$NAME" | tee drive.link
# replace previous mix 128k (moved to Drive trash, recoverable)
$R lsl "gdrive:" --include "DJ Grok Bot – Mix 08" --max-depth 1 && $R deletefile "gdrive:DJ Grok Bot – Mix 08" && echo "trashed Mix 08 128k"
bash ../../src/sync_icloud.sh dj-mix-09-320k.mp3 dj-mix-09-tracklist.md 9 "$NAME"
