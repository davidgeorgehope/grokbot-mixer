#!/usr/bin/env bash
# Usage: sync_set.sh <youtube_url> "<Artist/DJ>" [existing_local_audio_on_mini]
# Runs on the residential machine $HOST. Downloads (if needed) via yt-dlp + chrome cookies, keeps AAC as .m4a
# (smaller than 256k MP3, iOS-native), tags title/artist/album 'DJ Sets'/thumbnail cover,
# copies to iCloud 'DJ Mixes/Sets'. Never deletes source files.
set -euo pipefail
URL=$1; ARTIST=$2; LOCAL=${3:-}
HOST=${HOST:?set HOST (see config.example.env)}
ssh -o BatchMode=yes "$HOST" bash -s -- $(printf "%q " "$URL" "$ARTIST" "$LOCAL") <<'REMOTE'
set -euo pipefail
export PATH=$HOME/.ytdlp-nightly/bin:/opt/homebrew/bin:$PATH
URL=$1; ARTIST=$2; LOCAL=$3
DEST="$HOME/Library/Mobile Documents/com~apple~CloudDocs/DJ Mixes/Sets"; mkdir -p "$DEST" ~/prosets
W=$(mktemp -d)
IFS='|' read -r ID TITLE < <(yt-dlp </dev/null --cookies-from-browser chrome --skip-download --print "%(id)s|%(title)s" "$URL" 2>/dev/null)
yt-dlp </dev/null --cookies-from-browser chrome --skip-download --write-thumbnail --convert-thumbnails jpg -o "$W/thumb" "$URL" >/dev/null 2>&1
if [ -z "$LOCAL" ]; then LOCAL=~/prosets/$ID.m4a; [ -f "$LOCAL" ] || yt-dlp </dev/null --cookies-from-browser chrome -f 'ba[ext=m4a]' -o "$LOCAL" "$URL" >/dev/null 2>&1; fi
SAFE=$(echo "$TITLE" | tr '/:|' '-  ' | tr -s ' ')
OUT="$W/$SAFE.m4a"
ffmpeg -nostdin -loglevel error -y -i "$LOCAL" -i "$W/thumb.jpg" -map 0:a -map 1 -c copy -disposition:v attached_pic \
  -metadata title="$TITLE" -metadata artist="$ARTIST" -metadata album_artist="$ARTIST" \
  -metadata album="DJ Sets" -metadata genre="Drum & Bass" -metadata comment="$URL" -movflags +faststart "$OUT"
cp "$OUT" "$DEST/$SAFE.m4a.tmp" && mv "$DEST/$SAFE.m4a.tmp" "$DEST/$SAFE.m4a"
rm -rf "$W"; ls -la "$DEST/$SAFE.m4a"
REMOTE
