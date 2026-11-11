#!/usr/bin/env bash
# Runs on the pod. One short poll for the box side.
#   remote_status.sh <log_offset_bytes>
# First line: STATUS <running|done|fail:rc|dead|none> <progress_sig> <parts> <segs_done> <log_bytes>
# Then up to 64 KB of remote_run.log starting at <log_offset_bytes>.
TT_ROOT=${TT_ROOT:-/workspace/tt_viz}
cd "$TT_ROOT" 2>/dev/null || { echo "STATUS none 0 0 0 0"; exit 0; }
off=${1:-0}
st=none
if [ -f remote_run.done ]; then st=done
elif [ -f remote_run.fail ]; then st="fail:$(cat remote_run.fail)"
elif [ -s remote_run.pid ]; then
  if kill -0 "$(cat remote_run.pid)" 2>/dev/null; then st=running
  # wrapper writes the marker before exiting; re-check to avoid a race
  elif [ -f remote_run.done ]; then st=done
  elif [ -f remote_run.fail ]; then st="fail:$(cat remote_run.fail)"
  else st=dead; fi
fi
sig=$(du -sb work remote_run.log 2>/dev/null | awk '{s+=$1} END{print s+0}')
parts=$(ls work/seg*/part*.mp4 2>/dev/null | wc -l | tr -d ' ')
segs=$(ls work/seg*/done.marker 2>/dev/null | wc -l | tr -d ' ')
lsz=$(stat -c %s remote_run.log 2>/dev/null || echo 0)
echo "STATUS $st $sig $parts $segs $lsz"
if [ "$lsz" -gt "$off" ]; then tail -c +"$((off + 1))" remote_run.log | head -c 65536; fi
