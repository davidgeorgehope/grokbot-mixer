#!/usr/bin/env bash
# Rent a Runpod GPU, render a twin-turntable mix visual, pull the MP4 back, ALWAYS terminate the pod.
#
#   TIMING=... MIX=... OUT=... bash runpod_render.sh
#   META=...   MIX=... OUT=... [TRACKLIST=...] bash runpod_render.sh
#
# RUNPOD_API_KEY from env, else $HOME/.runpod_api_key (never printed).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
API_V2=https://api.runpod.io/v2

if [ -z "${RUNPOD_API_KEY:-}" ] && [ -f $HOME/.runpod_api_key ]; then
  RUNPOD_API_KEY=$(tr -d ' \n\r\t' < $HOME/.runpod_api_key)
  export RUNPOD_API_KEY
fi
[ -n "${RUNPOD_API_KEY:-}" ] || { echo "FATAL: RUNPOD_API_KEY missing" >&2; exit 2; }

MIX=${MIX:?set MIX}; OUT=${OUT:?set OUT}
GPU_TYPE=${GPU_TYPE:-}   # if set, try only this; else walk GPU_CANDIDATES
CLOUD=${CLOUD:-}         # if set, try only this; else COMMUNITY then SECURE
GPU_CANDIDATES=${GPU_CANDIDATES:-NVIDIA GeForce RTX 4090|NVIDIA L4|NVIDIA RTX A5000|NVIDIA GeForce RTX 3090|NVIDIA RTX A4000|NVIDIA L40S}
CLOUD_CANDIDATES=${CLOUD_CANDIDATES:-SECURE|COMMUNITY}
MAX_RUNTIME_SEC=${MAX_RUNTIME_SEC:-10800}
IMAGE=${IMAGE:-runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04}
NAME=${POD_NAME:-tt-viz-$(date +%Y%m%d%H%M%S)}
SSH_PUB=${SSH_PUB:-$HOME/.ssh/id_ed25519.pub}
SSH_PRIV=${SSH_PRIV:-$HOME/.ssh/id_ed25519}
STAGING=${STAGING:-/tmp/tt_runpod_$$}
POD_ID=""; COST_PER_HR=""; START_TS=$(date +%s); PUB_IP=""; SSH_PORT=""
WATCHDOG=""; STALL_WD=""
STALL_SEC=${STALL_SEC:-600}

log() { printf '[runpod_render] %s\n' "$*"; }
auth() { printf 'Authorization: Bearer %s' "$RUNPOD_API_KEY"; }

cleanup() {
  local rc=$?; set +e
  log "cleanup rc=$rc pod=${POD_ID:-none}"
  # Kill watchdogs first so a leftover sleep cannot SIGTERM a later PID.
  if [ -n "${STALL_WD:-}" ]; then kill "$STALL_WD" 2>/dev/null; wait "$STALL_WD" 2>/dev/null; fi
  if [ -n "${WATCHDOG:-}" ]; then kill "$WATCHDOG" 2>/dev/null; wait "$WATCHDOG" 2>/dev/null; fi
  if [ -n "${POD_ID:-}" ]; then
    curl -sS -m 30 -X DELETE -H "$(auth)" "$API_V2/pods/$POD_ID" >/dev/null 2>&1 || true
    log "terminate requested for $POD_ID"
  fi
  rm -rf "$STAGING"
  local wall=$(( $(date +%s) - START_TS ))
  if [ -n "$COST_PER_HR" ]; then
    python3 -c "print('[runpod_render] wall=${wall}s est_cost_usd=%.4f (rate=${COST_PER_HR}/hr)' % (${wall}/3600*float('${COST_PER_HR}')))"
  else
    log "wall=${wall}s"
  fi
  exit $rc
}
trap cleanup EXIT INT TERM

mkdir -p "$STAGING/in"
rsync -a --exclude node_modules --exclude '*.bak' --exclude 'tt_*' "$HERE/" "$STAGING/in/turntable_viz/"
cp /workspace/mixes/visuals/code/beatgrid_viz.py "$STAGING/in/beatgrid_viz.py"
if [ -d "$HERE/node_modules" ]; then
  rsync -a "$HERE/node_modules/" "$STAGING/in/turntable_viz/node_modules/"
fi

if [ -n "${TIMING:-}" ]; then
  cp "$TIMING" "$STAGING/in/timing.json"; MODE=timing
elif [ -n "${META:-}" ]; then
  cp "$META" "$STAGING/in/meta.json"; MODE=meta
  [ -n "${TRACKLIST:-}" ] && cp "$TRACKLIST" "$STAGING/in/tracklist.md"
else
  echo "set TIMING= or META=" >&2; exit 2
fi
cp "$MIX" "$STAGING/in/mix.audio"

python3 - <<PY
import json, os, shutil, sys
st_src="/workspace/mixes/src2/st"; src="/workspace/mixes/src2"
dst_st="$STAGING/in/st"; dst_src="$STAGING/in/src"
os.makedirs(dst_st, exist_ok=True); os.makedirs(dst_src, exist_ok=True)
ids=set()
if "$MODE"=="timing":
  for d in json.load(open("$STAGING/in/timing.json"))["decks"][:2]: ids.add(d["id"])
else:
  for d in json.load(open("$STAGING/in/meta.json"))["decks"]: ids.add(d["id"])
missing=[]
for i in sorted(ids):
  for ext in (".json",".sections.json"):
    p=f"{st_src}/{i}{ext}"
    if os.path.exists(p): shutil.copy2(p, f"{dst_st}/{i}{ext}")
  got=False
  for ext in (".m4a",".wav",".flac"):
    p=f"{src}/{i}{ext}"
    if os.path.exists(p): shutil.copy2(p, f"{dst_src}/{i}{ext}"); got=True; break
  if not got: missing.append(i)
print(f"packed {len(ids)} tracks")
if missing:
  print("MISSING audio for", missing); sys.exit(1)
PY

tar -C "$STAGING/in" -czf "$STAGING/payload.tgz" .
log "payload $(du -h "$STAGING/payload.tgz" | awk '{print $1}') mode=$MODE"

# Register SSH pubkey as a list of strings (v2 schema).
PUB=$(cat "$SSH_PUB")
reg=$(curl -sS -m 20 -w '\n%{http_code}' -X PUT -H "$(auth)" -H 'Content-Type: application/json' \
  -d "$(python3 -c "import json,sys;print(json.dumps({'keys':[sys.argv[1]]}))" "$PUB")" \
  "$API_V2/account/ssh-keys")
reg_code=$(echo "$reg" | tail -1)
[ "$reg_code" = 200 ] || log "ssh-key register http=$reg_code (continuing; PUBLIC_KEY env still set on pod)"

create_pod() {
  local cloud=$1 body resp code
  log "create cloud=$cloud gpu=$GPU_TYPE"
  export _RP_NAME="$NAME" _RP_IMAGE="$IMAGE" _RP_CLOUD="$cloud" _RP_GPU="$GPU_TYPE" _RP_SSH_PUB="$SSH_PUB"
  body=$(python3 - <<'PY'
import json, os
start = (
  "export DEBIAN_FRONTEND=noninteractive; "
  "apt-get update -qq; apt-get install -y -qq openssh-server >/dev/null; "
  "mkdir -p /var/run/sshd /root/.ssh; "
  'echo "$PUBLIC_KEY" > /root/.ssh/authorized_keys; '
  "chmod 700 /root/.ssh; chmod 600 /root/.ssh/authorized_keys; "
  "grep -q '^PermitRootLogin' /etc/ssh/sshd_config && "
  "sed -i 's/^PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config || "
  "echo 'PermitRootLogin yes' >> /etc/ssh/sshd_config; "
  "sed -i 's/^PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config; "
  "/usr/sbin/sshd; sleep infinity"
)
print(json.dumps({
  "name": os.environ["_RP_NAME"],
  "image": os.environ["_RP_IMAGE"],
  "cloud": os.environ["_RP_CLOUD"],
  "gpu": {"id": os.environ["_RP_GPU"], "count": 1},
  "disk": 40,
  "ports": ["22/tcp"],
  "startSsh": True,
  "env": {
    "PUBLIC_KEY": open(os.environ["_RP_SSH_PUB"]).read().strip(),
    "NVIDIA_DRIVER_CAPABILITIES": "compute,utility,graphics,display,video",
    "NVIDIA_VISIBLE_DEVICES": "all",
  },
  "cmd": ["bash", "-lc", start],
}))
PY
)
  resp=$(curl -sS -m 60 -w '\n%{http_code}' -X POST -H "$(auth)" -H 'Content-Type: application/json' -d "$body" "$API_V2/pods")
  code=$(echo "$resp" | tail -1); resp=$(echo "$resp" | sed '$d')
  if [ "$code" != 200 ] && [ "$code" != 201 ]; then
    log "create failed http=$code $(echo "$resp" | head -c 300)"; return 1
  fi
  POD_ID=$(echo "$resp" | python3 -c "import sys,json;print(json.load(sys.stdin).get('id') or '')")
  COST_PER_HR=$(echo "$resp" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('costPerHr') or d.get('cost') or '')")
  [ -n "$POD_ID" ] || return 1
  log "pod=$POD_ID rate=${COST_PER_HR:-?}/hr"
}

discard_pod() {
  local reason=$1
  if [ -n "${POD_ID:-}" ]; then
    log "discarding $POD_ID ($reason)"
    curl -sS -m 30 -X DELETE -H "$(auth)" "$API_V2/pods/$POD_ID" >/dev/null 2>&1 || true
    POD_ID=""; COST_PER_HR=""
  fi
}

# Direct public SSH only. Community pods often expose only the ssh.runpod.io
# proxy, which this box cannot use (resolver sinkholes that host; the proxy
# also requires a PTY and does not run remote commands or scp).
wait_direct_ssh() {
  local deadline st ip port
  PUB_IP=""; SSH_PORT=""
  deadline=$(( $(date +%s) + ${SSH_WAIT_SEC:-180} ))  # ~3 min, then try next type/tier
  while [ $(date +%s) -lt $deadline ]; do
    info=$(curl -sS -m 30 -H "$(auth)" "$API_V2/pods/$POD_ID")
    eval "$(echo "$info" | python3 -c "
import sys, json
d = json.load(sys.stdin)
st = d.get('status') or ''
ssh = (d.get('ssh') or {}).get('direct') or {}
host = ssh.get('host') or ''
port = str(ssh.get('port') or '')
if not host:
  for p in ((d.get('runtime') or {}).get('ports') or []):
    if p.get('private') in (22, '22'):
      host = p.get('ip') or ''
      port = str(p.get('public') or '')
      break
print(f'st={st!r}')
print(f'ip={host!r}')
print(f'port={port!r}')
")"
    log "wait status=$st ip=${ip:-?} port=${port:-?}"
    if [ "$st" = RUNNING ] && [ -n "$ip" ] && [ -n "$port" ]; then
      PUB_IP=$ip; SSH_PORT=$port; return 0
    fi
    sleep 5
  done
  return 1
}

# Walk cloud x GPU candidates until one deploys with direct SSH.
CLOUDS=()
if [ -n "$CLOUD" ]; then CLOUDS=("$CLOUD"); else IFS='|' read -ra CLOUDS <<<"$CLOUD_CANDIDATES"; fi
GPUS=()
if [ -n "$GPU_TYPE" ]; then GPUS=("$GPU_TYPE"); else IFS='|' read -ra GPUS <<<"$GPU_CANDIDATES"; fi
CREATED=0
for cloud in "${CLOUDS[@]}"; do
  for gpu in "${GPUS[@]}"; do
    GPU_TYPE="$gpu"
    log "trying cloud=$cloud gpu=$gpu"
    if create_pod "$cloud"; then
      log "deployed cloud=$cloud gpu=$GPU_TYPE pod=$POD_ID"
      if wait_direct_ssh; then
        CLOUD=$cloud
        CREATED=1
        break 2
      fi
      discard_pod "no direct SSH within ${SSH_WAIT_SEC:-180}s"
      if [ "$cloud" = COMMUNITY ]; then
        log "community has no direct SSH from this box; skipping remaining community types"
        break
      fi
    fi
  done
done
[ "$CREATED" = 1 ] || { log "no candidate deployed with direct SSH (clouds=${CLOUDS[*]} gpus=${GPUS[*]})"; exit 1; }

SSH=(ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR
     -o ConnectTimeout=15 -i "$SSH_PRIV" -p "$SSH_PORT")
SCP=(scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR
     -o ConnectTimeout=15 -i "$SSH_PRIV" -P "$SSH_PORT")
TARGET=root@$PUB_IP

for i in $(seq 1 60); do
  if "${SSH[@]}" "$TARGET" 'echo ssh_ok' 2>/dev/null; then break; fi
  sleep 3
  [ "$i" = 60 ] && { log "ssh never accepted"; exit 1; }
done
log "ssh ok $TARGET:$SSH_PORT"

( sleep "$MAX_RUNTIME_SEC"; log "MAX_RUNTIME_SEC hit"; kill -TERM $$ 2>/dev/null ) &
WATCHDOG=$!

"${SCP[@]}" "$STAGING/payload.tgz" "$TARGET:/tmp/tt_payload.tgz"
"${SSH[@]}" "$TARGET" 'rm -rf /workspace/tt_viz && mkdir -p /workspace/tt_viz && tar -C /workspace/tt_viz -xzf /tmp/tt_payload.tgz && rm -f /tmp/tt_payload.tgz'

# Line-buffered remote log (the Mix 08 first attempt looked stuck at Chrome because
# SSH stdout was block-buffered). Stall watchdog aborts if this file goes quiet.
: > "$STAGING/remote.out"
stall_watch() {
  local f=$1 last_sz=-1 last_change now sz
  last_change=$(date +%s)
  while true; do
    sleep 20
    sz=0
    [ -f "$f" ] && sz=$(wc -c < "$f" | tr -d " ")
    now=$(date +%s)
    if [ "$sz" -ne "$last_sz" ]; then
      last_sz=$sz
      last_change=$now
    elif [ $((now - last_change)) -ge "$STALL_SEC" ]; then
      log "STALL ${STALL_SEC}s with no remote output; aborting"
      kill -TERM $$ 2>/dev/null
      exit 1
    fi
  done
}
stall_watch "$STAGING/remote.out" &
STALL_WD=$!
log "remote_run start (stall=${STALL_SEC}s)"

# stdbuf so each log line reaches us immediately; tee keeps a remote copy too.
"${SSH[@]}" "$TARGET" "set -o pipefail; export PYTHONUNBUFFERED=1 CHUNK_FRAMES=${CHUNK_FRAMES:-900} GROOVE_DIVE=${GROOVE_DIVE:-1} FORCE_DIVE=${FORCE_DIVE:-0} WORKERS=${WORKERS:-1} TT_GL_OVERRIDE=${TT_GL_OVERRIDE:-}; stdbuf -oL -eL bash /workspace/tt_viz/turntable_viz/remote_run.sh 2>&1 | stdbuf -oL -eL tee /workspace/tt_viz/remote_run.log" \
  | stdbuf -oL -eL tee -a "$STAGING/remote.out"

mkdir -p "$(dirname "$OUT")"
"${SCP[@]}" "$TARGET:/workspace/tt_viz/out.mp4" "$OUT"
ffprobe -v error -show_entries format=duration:stream=codec_name,width,height -of compact "$OUT"
log "pulled $OUT"
kill ${STALL_WD:-} ${WATCHDOG:-} 2>/dev/null || true
STALL_WD=""; WATCHDOG=""
