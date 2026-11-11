#!/usr/bin/env bash
# Runs on the pod. Start remote_run.sh fully detached from the ssh session
# (setsid + nohup, stdio on files), so a dropped ssh channel can never SIGPIPE
# or SIGHUP the render. Writes:
#   $TT_ROOT/remote_run.pid   wrapper pid
#   $TT_ROOT/remote_run.log   render log (appended)
#   $TT_ROOT/remote_run.done  on rc=0 (contains rc)
#   $TT_ROOT/remote_run.fail  on rc!=0 (contains rc)
# Idempotent: if a run is already alive, report it and do nothing.
set -euo pipefail
TT_ROOT=${TT_ROOT:-/workspace/tt_viz}
cd "$TT_ROOT"
if [ -s remote_run.pid ] && kill -0 "$(cat remote_run.pid)" 2>/dev/null; then
  echo "ALREADY_RUNNING pid=$(cat remote_run.pid)"; exit 0
fi
rm -f remote_run.done remote_run.fail
off=$(stat -c %s remote_run.log 2>/dev/null || echo 0)
printf '[remote_detach] start %s resume=%s\n' "$(date -u +%FT%TZ)" "${RESUME:-0}" >> remote_run.log
setsid nohup bash -c '
  root=$1
  bash "$root/turntable_viz/remote_run.sh" >> "$root/remote_run.log" 2>&1 < /dev/null
  rc=$?
  if [ "$rc" -eq 0 ]; then echo "$rc" > "$root/remote_run.done"; else echo "$rc" > "$root/remote_run.fail"; fi
' _ "$TT_ROOT" > /dev/null 2>&1 < /dev/null &
echo $! > remote_run.pid
echo "LAUNCHED pid=$(cat remote_run.pid) logoff=$off"
