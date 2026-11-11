#!/usr/bin/env bash
# Rent a Runpod GPU, render a twin-turntable mix visual, pull the MP4 back, ALWAYS terminate the pod.
#
#   TIMING=... MIX=... OUT=... bash runpod_render.sh
#   META=...   MIX=... OUT=... [TRACKLIST=...] [MASTER=...] bash runpod_render.sh
#
# RUNPOD_API_KEY from env, else $HOME/.runpod_api_key (never printed).
#
# Payload: lossless source audio is transcoded to 320k AAC before upload; the mix
# is sent as a 64k mono proxy when MASTER is set. The payload is streamed
# (tar | gzip | ssh) so a 200MB tarball is never held in memory or written to
# disk. After pull, the master is muxed locally at 320k AAC.
#
# Upload guard: if throughput is under MIN_UPLOAD_BPS (default 1 MB/s) after
# UPLOAD_PROBE_SEC (default 60), the pod is terminated and the next GPU type /
# datacenter is tried. MAX_RUNTIME_SEC defaults to 2.5x mix duration + 30 min.
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
# Prefer North-American DCs (this box peers poorly to some far regions; a 50 KB/s
# upload burned a 3h watchdog). Empty DATA_CENTER_CANDIDATES lets the scheduler pick.
DATA_CENTER_CANDIDATES=${DATA_CENTER_CANDIDATES:-US-MD-1|US-PA-1|US-NC-1|US-NC-2|US-GA-2|US-IL-1|US-TX-3|US-TX-4|US-MO-1|US-MO-2|US-KS-2|US-NE-1|CA-MTL-1|CA-MTL-3|CA-MTL-4|US-CO-1|US-WA-1|US-WA-2|US-CA-2}
IMAGE=${IMAGE:-runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04}
NAME_BASE=${POD_NAME:-tt-viz-$(date +%Y%m%d%H%M%S)}
NAME=$NAME_BASE
SSH_PUB=${SSH_PUB:-$HOME/.ssh/id_ed25519.pub}
SSH_PRIV=${SSH_PRIV:-$HOME/.ssh/id_ed25519}
STAGING=${STAGING:-/tmp/tt_runpod_$$}
ACTIVE_PODS=${ACTIVE_PODS:-/workspace/mixes/jobs/runpod-active.pods}
SPEND_LOG=${SPEND_LOG:-/workspace/mixes/jobs/runpod-spend.log}
MAX_SPEND_USD=${MAX_SPEND_USD:-5}
MIN_UPLOAD_BPS=${MIN_UPLOAD_BPS:-1000000}
UPLOAD_PROBE_SEC=${UPLOAD_PROBE_SEC:-60}
STALL_SEC=${STALL_SEC:-600}
POD_ID=""; COST_PER_HR=""; POD_DC=""; POD_START_TS=""
START_TS=$(date +%s); PUB_IP=""; SSH_PORT=""
WATCHDOG=""; STALL_WD=""
CLEANING=""; ATTEMPT=0
DENIED_DCS=""
SPENT_SESSION=0

log() { printf '[runpod_render] %s\n' "$*"; }
auth() { printf 'Authorization: Bearer %s' "$RUNPOD_API_KEY"; }

# Background + wait so a trap can run immediately (bash defers traps until a
# foreground external command exits; wait is interruptible).
run_wait() {
  "$@" &
  local pid=$! rc=0
  wait "$pid" || rc=$?
  return $rc
}

kill_descendants() {
  local p=${1:-$$} c
  for c in $(pgrep -P "$p" 2>/dev/null || true); do
    kill_descendants "$c"
    kill -TERM "$c" 2>/dev/null || true
  done
}

spend_so_far() {
  python3 - "$SPEND_LOG" <<'PY1'
import sys
path = sys.argv[1]
total = 0.0
try:
    for line in open(path):
        line=line.strip()
        if not line or line.startswith("#"):
            continue
        parts=line.split()
        if len(parts) >= 5:
            try: total += float(parts[4])
            except ValueError: pass
except FileNotFoundError:
    pass
print(f"{total:.4f}")
PY1
}

record_spend() {
  local pod=${1:-unknown} rate=${2:-0} wall=${3:-0} reason=${4:-}
  local est
  est=$(python3 -c "print(f'{(float('${wall}')/3600)*float('${rate}' or 0):.4f}')")
  mkdir -p "$(dirname "$SPEND_LOG")"
  printf '%s  %s  %s  %s  %s  %s\n' "$(date +%Y-%m-%dT%H:%M:%S%z)" "$pod" "${rate:-0}" "$wall" "$est" "$reason" >> "$SPEND_LOG"
  log "spend +${est} usd (pod=$pod wall=${wall}s rate=${rate}/hr reason=$reason) total=$(spend_so_far)"
}

note_active() {
  mkdir -p "$(dirname "$ACTIVE_PODS")"
  if [ -n "${POD_ID:-}" ]; then
    if [ ! -f "$ACTIVE_PODS" ] || ! grep -qx "$POD_ID" "$ACTIVE_PODS" 2>/dev/null; then
      printf '%s\n' "$POD_ID" >> "$ACTIVE_PODS"
    fi
  fi
}

clear_active() {
  local id=$1
  [ -n "$id" ] && [ -f "$ACTIVE_PODS" ] || return 0
  python3 - "$ACTIVE_PODS" "$id" <<'PY2'
import sys, pathlib
p, drop = pathlib.Path(sys.argv[1]), sys.argv[2]
if p.exists():
    lines=[ln for ln in p.read_text().splitlines() if ln.strip() and ln.strip()!=drop]
    p.write_text(("\n".join(lines)+("\n" if lines else "")))
PY2
}

terminate_pod() {
  local id=$1 reason=${2:-cleanup} tries=0 st
  [ -n "$id" ] || return 0
  log "terminate requested for $id ($reason)"
  while [ $tries -lt 3 ]; do
    curl -sS -m 30 -X DELETE -H "$(auth)" "$API_V2/pods/$id" >/dev/null 2>&1 || true
    sleep 2
    st=$(curl -sS -m 20 -H "$(auth)" "$API_V2/pods/$id" 2>/dev/null | python3 -c "import sys,json
try:
 d=json.load(sys.stdin); print((d.get('status') or d.get('desiredStatus') or '').upper())
except Exception:
 print('GONE')
" 2>/dev/null || echo GONE)
    if [ -z "$st" ] || [ "$st" = GONE ] || [ "$st" = EXITED ] || [ "$st" = TERMINATED ] || [ "$st" = "NOT FOUND" ]; then
      break
    fi
    echo "$st" | grep -qi 'NOT' && break
    tries=$((tries+1))
  done
  clear_active "$id"
}

reap_stale_pods() {
  local id info st
  [ -f "$ACTIVE_PODS" ] || return 0
  while read -r id; do
    [ -n "$id" ] || continue
    info=$(curl -sS -m 20 -H "$(auth)" "$API_V2/pods/$id" 2>/dev/null || true)
    st=$(printf '%s' "$info" | python3 -c "import sys,json
t=sys.stdin.read()
try:
 d=json.loads(t); print((d.get('status') or d.get('id') or ''))
except Exception:
 print('')
" 2>/dev/null || true)
    if [ -n "$st" ] && [ "$st" != "None" ]; then
      log "reaping leftover pod $id"
      terminate_pod "$id" "stale-active-file"
    else
      clear_active "$id"
    fi
  done < "$ACTIVE_PODS"
}

# Confirm the API lists no leftover pods from this script (name prefix tt-viz-).
verify_no_ours() {
  local leftover
  leftover=$(curl -sS -m 20 -H "$(auth)" "$API_V2/pods" 2>/dev/null | python3 -c "
import sys,json,os
try: d=json.load(sys.stdin)
except Exception: print(''); raise SystemExit
pods=d if isinstance(d,list) else d.get('pods') or []
active=set()
ap=os.environ.get('ACTIVE_PODS_PATH','')
if ap and os.path.exists(ap):
    active=set(x.strip() for x in open(ap) if x.strip())
ids=[]
for p in pods:
    name=p.get('name') or ''
    pid=p.get('id') or ''
    if name.startswith('tt-viz-') or pid in active:
        ids.append(pid)
print(' '.join(ids))
" 2>/dev/null || true)
  if [ -n "${leftover:-}" ]; then
    log "WARNING leftover pods still listed: $leftover — terminating"
    for id in $leftover; do terminate_pod "$id" "verify-leftover"; done
  fi
}

budget_or_die() {
  local spent
  spent=$(spend_so_far)
  python3 -c "import sys; spent=float('$spent'); maxs=float('$MAX_SPEND_USD'); need=float('$1');
print(f'budget spent={spent:.4f} max={maxs:.2f} need={need:.2f}')
sys.exit(0 if spent+need <= maxs+1e-6 else 2)"
}

cleanup() {
  local rc=$?
  if [ -n "${CLEANING:-}" ]; then return 0; fi
  CLEANING=1
  set +e
  log "cleanup rc=$rc pod=${POD_ID:-none}"
  if [ -n "${STALL_WD:-}" ]; then kill "$STALL_WD" 2>/dev/null; fi
  if [ -n "${WATCHDOG:-}" ]; then kill "$WATCHDOG" 2>/dev/null; fi
  kill_descendants $$
  if [ -n "${POD_ID:-}" ]; then
    local wall=0
    if [ -n "${POD_START_TS:-}" ]; then wall=$(( $(date +%s) - POD_START_TS )); fi
    terminate_pod "$POD_ID" "trap-rc=$rc"
    if [ -n "$COST_PER_HR" ]; then record_spend "$POD_ID" "$COST_PER_HR" "$wall" "trap-rc=$rc"; fi
    POD_ID=""; COST_PER_HR=""
  fi
  verify_no_ours
  rm -rf "$STAGING"
  local wall_all=$(( $(date +%s) - START_TS ))
  log "wall=${wall_all}s spent_total=$(spend_so_far)"
}

trap cleanup EXIT
trap 'exit 143' INT TERM

export ACTIVE_PODS_PATH="$ACTIVE_PODS"
reap_stale_pods

mkdir -p "$STAGING/in"

# --- pack payload (compact audio, pruned node_modules; no tarball on disk) ---
rsync -a --exclude node_modules --exclude '*.bak' --exclude 'tt_*' --exclude '__pycache__' \
  "$HERE/" "$STAGING/in/turntable_viz/"
cp /workspace/mixes/visuals/code/beatgrid_viz.py "$STAGING/in/beatgrid_viz.py"
if [ -d "$HERE/node_modules" ]; then
  rsync -a --exclude '*.map' --exclude '*.d.ts' --exclude '*.md' --exclude '*.markdown' \
    --exclude 'test/' --exclude 'tests/' --exclude '__tests__/' \
    "$HERE/node_modules/" "$STAGING/in/turntable_viz/node_modules/"
fi

if [ -n "${TIMING:-}" ]; then
  cp "$TIMING" "$STAGING/in/timing.json"; MODE=timing
elif [ -n "${META:-}" ]; then
  cp "$META" "$STAGING/in/meta.json"; MODE=meta
  [ -n "${TRACKLIST:-}" ] && cp "$TRACKLIST" "$STAGING/in/tracklist.md"
else
  echo "set TIMING= or META=" >&2; exit 2
fi

MIX_DUR=$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$MIX")
# 2.5x mix duration + 30 min, floor 45 min. Override with MAX_RUNTIME_SEC=...
if [ -z "${MAX_RUNTIME_SEC:-}" ]; then
  MAX_RUNTIME_SEC=$(python3 -c "print(int(max(2700, 2.5*float('${MIX_DUR}') + 1800)))")
fi
log "mix_dur=${MIX_DUR}s MAX_RUNTIME_SEC=$MAX_RUNTIME_SEC"

# Visualization proxy when we will remux the master locally after pull.
if [ -n "${MASTER:-}" ] && [ -f "$MASTER" ]; then
  log "encoding 64k mono mix proxy (master remux after pull)"
  ffmpeg -nostdin -y -loglevel error -i "$MIX" -ac 1 -ar 22050 -c:a libmp3lame -b:a 64k \
    -f mp3 "$STAGING/in/mix.audio" </dev/null
  SKIP_AUDIO_MUX=${SKIP_AUDIO_MUX:-1}
else
  cp "$MIX" "$STAGING/in/mix.audio"
  SKIP_AUDIO_MUX=${SKIP_AUDIO_MUX:-0}
fi
export SKIP_AUDIO_MUX
export TT_DST_ST="$STAGING/in/st" TT_DST_SRC="$STAGING/in/src" TT_MODE="$MODE" TT_STAGING_IN="$STAGING/in"

python3 - <<'PY3'
import json, os, shutil, subprocess, sys
st_src="/workspace/mixes/src2/st"; src="/workspace/mixes/src2"
dst_st=os.environ["TT_DST_ST"]; dst_src=os.environ["TT_DST_SRC"]
mode=os.environ["TT_MODE"]
staging_in=os.environ["TT_STAGING_IN"]
os.makedirs(dst_st, exist_ok=True); os.makedirs(dst_src, exist_ok=True)
ids=set()
if mode=="timing":
  for d in json.load(open(os.path.join(staging_in,"timing.json")))["decks"][:2]: ids.add(d["id"])
else:
  for d in json.load(open(os.path.join(staging_in,"meta.json")))["decks"]: ids.add(d["id"])
missing=[]
missing_st=[]
n_copy=n_xcode=0
for i in sorted(ids):
  st_json=f"{st_src}/{i}.json"
  if not os.path.exists(st_json):
    missing_st.append(i)
    continue
  shutil.copy2(st_json, f"{dst_st}/{i}.json")
  sec=f"{st_src}/{i}.sections.json"
  if os.path.exists(sec):
    shutil.copy2(sec, f"{dst_st}/{i}.sections.json")
  m4a=f"{dst_src}/{i}.m4a"
  src_m4a=f"{src}/{i}.m4a"
  if os.path.exists(src_m4a):
    shutil.copy2(src_m4a, m4a); n_copy+=1; continue
  lossless=next((f"{src}/{i}{ext}" for ext in (".flac",".wav") if os.path.exists(f"{src}/{i}{ext}")), None)
  if lossless:
    subprocess.check_call([
      "ffmpeg","-nostdin","-y","-loglevel","error","-i",lossless,
      "-c:a","aac","-b:a","320k","-movflags","+faststart",m4a
    ], stdin=subprocess.DEVNULL)
    n_xcode+=1; continue
  compact=next((f"{src}/{i}{ext}" for ext in (".mp3",".opus",".ogg") if os.path.exists(f"{src}/{i}{ext}")), None)
  if compact:
    shutil.copy2(compact, f"{dst_src}/{i}{os.path.splitext(compact)[1]}"); n_copy+=1; continue
  missing.append(i)
print(f"packed {len(ids)} tracks (copied={n_copy} transcoded_320k={n_xcode})")
if missing_st:
  print("MISSING analysis (st/<id>.json) for", missing_st); sys.exit(1)
if missing:
  print("MISSING audio for", missing); sys.exit(1)
# Fail closed: every packed track must have analysis in the staged tree.
staged_missing=[i for i in sorted(ids) if not os.path.exists(f"{dst_st}/{i}.json")]
if staged_missing:
  print("STAGED analysis missing for", staged_missing); sys.exit(1)
print(f"preflight ok: {len(ids)} analysis files in payload")
PY3


# Report payload size by streaming through gzip once — never write the tarball.
PAYLOAD_BYTES=$(tar -C "$STAGING/in" -cf - \
  --exclude='*.map' --exclude='*.d.ts' --exclude='__pycache__' . \
  | gzip -1 | wc -c | tr -d ' ')
log "payload $(python3 -c "b=int('${PAYLOAD_BYTES}'); print(f'{b/1e6:.1f}MB ({b} bytes)')") mode=$MODE (streamed, not written to disk)"
python3 - "$STAGING/in" <<'PY4'
import os, sys
root=sys.argv[1]
rows=[]
for dp, dns, fns in os.walk(root):
    for fn in fns:
        p=os.path.join(dp,fn)
        try: rows.append((os.path.getsize(p), os.path.relpath(p, root)))
        except OSError: pass
rows.sort(reverse=True)
print("[runpod_render] top staged files:")
for sz, rel in rows[:8]:
    print(f"  {sz/1e6:7.1f} MB  {rel}")
print(f"[runpod_render] staged_tree {sum(s for s,_ in rows)/1e6:.1f} MB uncompressed")
PY4

if [ "${PACK_ONLY:-0}" = 1 ]; then
  log "PACK_ONLY=1, not creating a pod"
  exit 0
fi

# Need ~2 hours of 4090 time plus slack. Refuse a new pod if we cannot afford it.
EST_RENDER_USD=$(python3 -c "dur=float('${MIX_DUR}'); rate=0.89; hours=(dur/0.56 + 1200)/3600; print(f'{hours*rate:.2f}')")
log "est_full_render_usd=${EST_RENDER_USD} (0.56x realtime + 20 min at 0.89/hr)"
budget_or_die "$EST_RENDER_USD" || { log "FATAL: spend budget would exceed \$${MAX_SPEND_USD} (need ${EST_RENDER_USD} more)"; exit 2; }

# Register SSH pubkey as a list of strings (v2 schema).
PUB=$(cat "$SSH_PUB")
reg=$(curl -sS -m 20 -w '\n%{http_code}' -X PUT -H "$(auth)" -H 'Content-Type: application/json' \
  -d "$(python3 -c "import json,sys;print(json.dumps({'keys':[sys.argv[1]]}))" "$PUB")" \
  "$API_V2/account/ssh-keys")
reg_code=$(echo "$reg" | tail -1)
[ "$reg_code" = 200 ] || log "ssh-key register http=$reg_code (continuing; PUBLIC_KEY env still set on pod)"

create_pod() {
  local cloud=$1 dcs=${2:-} body resp code
  ATTEMPT=$((ATTEMPT+1))
  NAME="${NAME_BASE}-a${ATTEMPT}"
  log "create cloud=$cloud gpu=$GPU_TYPE dc=${dcs:-any}"
  export _RP_NAME="$NAME" _RP_IMAGE="$IMAGE" _RP_CLOUD="$cloud" _RP_GPU="$GPU_TYPE" _RP_SSH_PUB="$SSH_PUB" _RP_DCS="$dcs"
  body=$(python3 - <<'PY5'
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
body = {
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
}
dcs = [x for x in os.environ.get("_RP_DCS","").split("|") if x]
if dcs:
    body["dataCenterIds"] = dcs
print(json.dumps(body))
PY5
)
  resp=$(curl -sS -m 60 -w '\n%{http_code}' -X POST -H "$(auth)" -H 'Content-Type: application/json' -d "$body" "$API_V2/pods")
  code=$(echo "$resp" | tail -1); resp=$(echo "$resp" | sed '$d')
  if [ "$code" != 200 ] && [ "$code" != 201 ]; then
    log "create failed http=$code $(echo "$resp" | head -c 300)"; return 1
  fi
  POD_ID=$(echo "$resp" | python3 -c "import sys,json;print(json.load(sys.stdin).get('id') or '')")
  COST_PER_HR=$(echo "$resp" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('costPerHr') or d.get('cost') or '')")
  POD_DC=$(echo "$resp" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('dataCenterId') or '')")
  [ -n "$POD_ID" ] || return 1
  POD_START_TS=$(date +%s)
  note_active
  log "pod=$POD_ID rate=${COST_PER_HR:-?}/hr dc=${POD_DC:-?}"
}

discard_pod() {
  local reason=$1 wall=0
  if [ -n "${POD_ID:-}" ]; then
    if [ -n "${POD_START_TS:-}" ]; then wall=$(( $(date +%s) - POD_START_TS )); fi
    log "discarding $POD_ID ($reason)"
    terminate_pod "$POD_ID" "$reason"
    if [ -n "$COST_PER_HR" ]; then record_spend "$POD_ID" "$COST_PER_HR" "$wall" "$reason"; fi
    POD_ID=""; COST_PER_HR=""; POD_DC=""; POD_START_TS=""; PUB_IP=""; SSH_PORT=""
  fi
}

# Direct public SSH only. Community pods often expose only the ssh.runpod.io
# proxy, which this box cannot use (resolver sinkholes that host; the proxy
# also requires a PTY and does not run remote commands or scp).
wait_direct_ssh() {
  local deadline st ip port dc
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
dc = d.get('dataCenterId') or ''
if not host:
  for p in ((d.get('runtime') or {}).get('ports') or []):
    if p.get('private') in (22, '22'):
      host = p.get('ip') or ''
      port = str(p.get('public') or '')
      break
print(f'st={st!r}')
print(f'ip={host!r}')
print(f'port={port!r}')
print(f'dc={dc!r}')
")"
    if [ -n "${dc:-}" ]; then POD_DC=$dc; fi
    log "wait status=$st ip=${ip:-?} port=${port:-?} dc=${POD_DC:-?}"
    if [ "$st" = RUNNING ] && [ -n "$ip" ] && [ -n "$port" ]; then
      PUB_IP=$ip; SSH_PORT=$port; return 0
    fi
    sleep 5
  done
  return 1
}

deny_dc() {
  local dc=$1
  [ -n "$dc" ] || return 0
  case "|$DENIED_DCS|" in
    *"|$dc|"*) ;;
    *) DENIED_DCS="${DENIED_DCS:+$DENIED_DCS|}$dc"; log "denylisted dc=$dc" ;;
  esac
}

remaining_dcs() {
  python3 -c "
cands='${DATA_CENTER_CANDIDATES}'.split('|') if '${DATA_CENTER_CANDIDATES}' else []
denied=set(x for x in '${DENIED_DCS}'.split('|') if x)
print('|'.join(x for x in cands if x and x not in denied))
"
}

wait_ssh_accept() {
  local ssh_deadline i ssh_ok err
  SSH=(ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR
       -o ConnectTimeout=8 -i "$SSH_PRIV" -p "$SSH_PORT")
  TARGET=root@$PUB_IP
  ssh_deadline=$(( $(date +%s) + ${SSH_ACCEPT_SEC:-600} ))
  i=0
  ssh_ok=0
  while [ $(date +%s) -lt $ssh_deadline ]; do
    i=$((i + 1))
    if run_wait "${SSH[@]}" "$TARGET" 'echo ssh_ok' >"$STAGING/ssh.out" 2>"$STAGING/ssh.err"; then
      if grep -q ssh_ok "$STAGING/ssh.out"; then ssh_ok=1; break; fi
    fi
    if [ $((i % 6)) -eq 1 ]; then
      err=$(tr '\n' ' ' < "$STAGING/ssh.err" 2>/dev/null | tr -d '\r' | tail -c 180)
      log "ssh not ready try=$i err=${err:-none}"
    fi
    sleep 4
  done
  [ "$ssh_ok" = 1 ] || return 1
  log "ssh ok $TARGET:$SSH_PORT dc=${POD_DC:-?}"
}

# Stream tar|gzip through the speed guard into remote tar -xzf. No tarball on disk.
stream_upload() {
  local rc=0 pid
  log "streaming payload (${PAYLOAD_BYTES} bytes gz, abort if under ${MIN_UPLOAD_BPS} B/s after ${UPLOAD_PROBE_SEC}s)"
  set +e
  (
    set -o pipefail
    tar -C "$STAGING/in" -cf - --exclude='*.map' --exclude='*.d.ts' --exclude='__pycache__' . \
      | gzip -1 \
      | python3 "$HERE/stream_guard.py" --probe-sec "$UPLOAD_PROBE_SEC" --min-bps "$MIN_UPLOAD_BPS" --prefix "[runpod_render]" \
      | "${SSH[@]}" -o ConnectTimeout=15 "$TARGET" 'rm -rf /workspace/tt_viz && mkdir -p /workspace/tt_viz && tar -C /workspace/tt_viz -xzf -'
  ) &
  pid=$!
  wait "$pid"
  rc=$?
  set -e
  return $rc
}

# Walk cloud x GPU x remaining datacenters until one deploys with direct SSH and a fast upload.
CLOUDS=()
if [ -n "$CLOUD" ]; then CLOUDS=("$CLOUD"); else IFS='|' read -ra CLOUDS <<<"$CLOUD_CANDIDATES"; fi
GPUS=()
if [ -n "$GPU_TYPE" ]; then GPUS=("$GPU_TYPE"); else IFS='|' read -ra GPUS <<<"$GPU_CANDIDATES"; fi
CREATED=0
UNCONSTRAINED=0
for cloud in "${CLOUDS[@]}"; do
  for gpu in "${GPUS[@]}"; do
    GPU_TYPE="$gpu"
    while true; do
      local_dcs=$(remaining_dcs)
      if [ -z "$local_dcs" ]; then
        if [ "$UNCONSTRAINED" = 1 ]; then
          log "no remaining datacenters and unconstrained already tried for this gpu"
          break
        fi
        log "preferred datacenters exhausted; retrying without a DC filter"
        UNCONSTRAINED=1
      fi
      spent_now=$(spend_so_far)
      log "trying cloud=$cloud gpu=$gpu dc=${local_dcs:-any} spent=${spent_now}"
      budget_or_die "$EST_RENDER_USD" || { log "FATAL: spend budget would exceed \$${MAX_SPEND_USD}"; exit 2; }
      if create_pod "$cloud" "$local_dcs"; then
        log "deployed cloud=$cloud gpu=$GPU_TYPE pod=$POD_ID dc=${POD_DC:-?}"
        if ! wait_direct_ssh; then
          discard_pod "no direct SSH within ${SSH_WAIT_SEC:-180}s"
          if [ "$cloud" = COMMUNITY ]; then
            log "community has no direct SSH from this box; skipping remaining community types"
            break 2
          fi
          break
        fi
        if ! wait_ssh_accept; then
          [ -n "$POD_DC" ] && deny_dc "$POD_DC"
          discard_pod "ssh never accepted after ${SSH_ACCEPT_SEC:-600}s"
          continue
        fi
        if stream_upload; then
          CREATED=1
          break 3
        else
          up_rc=$?
          if [ "$up_rc" = 7 ]; then
            [ -n "$POD_DC" ] && deny_dc "$POD_DC"
            discard_pod "upload too slow (<${MIN_UPLOAD_BPS} B/s after ${UPLOAD_PROBE_SEC}s) dc=${POD_DC:-?}"
            continue
          fi
          discard_pod "upload failed rc=$up_rc"
          continue
        fi
      else
        break
      fi
    done
  done
done
[ "$CREATED" = 1 ] || { log "no candidate deployed with direct SSH and a fast upload (clouds=${CLOUDS[*]} gpus=${GPUS[*]})"; exit 1; }

SSH=(ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR
     -o ConnectTimeout=8 -i "$SSH_PRIV" -p "$SSH_PORT")
SCP=(scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR
     -o ConnectTimeout=15 -i "$SSH_PRIV" -P "$SSH_PORT")
TARGET=root@$PUB_IP

( sleep "$MAX_RUNTIME_SEC"; log "MAX_RUNTIME_SEC hit"; kill -TERM $$ 2>/dev/null ) &
WATCHDOG=$!

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
log "remote_run start (stall=${STALL_SEC}s max=${MAX_RUNTIME_SEC}s skip_audio_mux=${SKIP_AUDIO_MUX})"

# stdbuf so each log line reaches us immediately; tee keeps a remote copy too.
# Process substitution + run_wait: the main shell blocks in wait, so TERM traps
# run immediately (a foreground pipe would defer them).
run_wait "${SSH[@]}" "$TARGET" "set -o pipefail; export PYTHONUNBUFFERED=1 CHUNK_FRAMES=${CHUNK_FRAMES:-900} GROOVE_DIVE=${GROOVE_DIVE:-1} FORCE_DIVE=${FORCE_DIVE:-0} WORKERS=${WORKERS:-1} TT_GL_OVERRIDE=${TT_GL_OVERRIDE:-} SKIP_AUDIO_MUX=${SKIP_AUDIO_MUX:-0}; stdbuf -oL -eL bash /workspace/tt_viz/turntable_viz/remote_run.sh 2>&1 | stdbuf -oL -eL tee /workspace/tt_viz/remote_run.log" \
  > >(stdbuf -oL -eL tee -a "$STAGING/remote.out")

mkdir -p "$(dirname "$OUT")"
PULL_TMP=${OUT}.pulled.mp4
run_wait "${SCP[@]}" "$TARGET:/workspace/tt_viz/out.mp4" "$PULL_TMP"
ffprobe -v error -show_entries format=duration:stream=codec_name,width,height -of compact "$PULL_TMP"

if [ -n "${MASTER:-}" ] && [ -f "$MASTER" ]; then
  log "muxing master audio at 320k AAC into $OUT"
  ffmpeg -nostdin -y -loglevel error -i "$PULL_TMP" -i "$MASTER" \
    -map 0:v -map 1:a -c:v copy -c:a aac -b:a 320k -ar 44100 -ac 2 -shortest -movflags +faststart \
    "$OUT" </dev/null
  rm -f "$PULL_TMP"
else
  mv "$PULL_TMP" "$OUT"
fi
ffprobe -v error -show_entries format=duration:stream=codec_name,width,height -of compact "$OUT"
log "pulled $OUT"
kill ${STALL_WD:-} ${WATCHDOG:-} 2>/dev/null || true
STALL_WD=""; WATCHDOG=""
