#!/usr/bin/env bash
# Usage: sync_icloud.sh <master.mp3> <tracklist.md> <track_no> "<Title>"
# Atomic: stage in /tmp on the Mac then mv, so iCloud never uploads a partial file.
# Tags (ID3 + generated cover), copies to $HOST iCloud Drive "DJ Mixes". Never deletes.
set -euo pipefail
SRC=$1; TL=$2; N=$3; TITLE=$4
HOST=${HOST:?set HOST (see config.example.env)}; DEST=${ICLOUD_DEST:-'Library/Mobile Documents/com~apple~CloudDocs/DJ Mixes'}; ART=${TAG_ARTIST:-DJ Grok Bot}
TMP=$(mktemp -d); OUT="$TMP/$TITLE.mp3"
ffmpeg -loglevel error -y -f lavfi -i "gradient=s=1000x1000:c0=0x1a0b3d:c1=0x00c2c7:d=1,drawtext=text='$TITLE':fontcolor=white:fontsize=64:x=(w-tw)/2:y=(h-th)/2" -frames:v 1 "$TMP/cover.jpg" 2>/dev/null \
 || ffmpeg -loglevel error -y -f lavfi -i "color=c=0x1a0b3d:s=1000x1000,drawtext=text='$TITLE':fontcolor=white:fontsize=64:x=(w-tw)/2:y=(h-th)/2" -frames:v 1 "$TMP/cover.jpg"
ffmpeg -loglevel error -y -i "$SRC" -i "$TMP/cover.jpg" -map 0:a -map 1 -c copy -id3v2_version 3 \
  -metadata title="$TITLE" -metadata artist="$ART" -metadata album_artist="$ART" \
  -metadata album="DJ Mixes" -metadata track="$N" -metadata genre="Drum & Bass" \
  -metadata:s:v title="Album cover" -metadata:s:v comment="Cover (front)" "$OUT"
cp "$TL" "$TMP/$TITLE - Tracklist.txt"
ssh -o BatchMode=yes "$HOST" "mkdir -p ~/'$DEST'"
for f in "$OUT" "$TMP/$TITLE - Tracklist.txt"; do b=$(basename "$f"); ssh -o BatchMode=yes "$HOST" "cat > /tmp/.sync_\$\$ && mv -f /tmp/.sync_\$\$ ~/'$DEST'/'$b'" < "$f"; done
ssh -o BatchMode=yes "$HOST" "cd ~/'$DEST' && ls -la && brctl status com.apple.CloudDocs 2>&1 | head -20"
rm -rf "$TMP"
