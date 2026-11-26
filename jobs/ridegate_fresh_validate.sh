#!/usr/bin/env bash
# Fresh-mix validation (ukf_drum_bass_wVp_VlkWqxI, 18 pairs): default vs
# RIDEGATE=1 vs RIDEGATE=1+LINGER_GUARD. Does not open the locked holdout.
# Does not write rules.json. Restores missing source audio into a scratch dir,
# then renders via eval_gate (unique per-variant tags).
set -euo pipefail
cd /workspace/mixes
# Wait for the usual render-slot jobs; do not start a holdout.
while grep -q '^running' jobs/fit-pro-fade-6.status 2>/dev/null \
   || grep -q '^running' jobs/render-n1126.status 2>/dev/null \
   || grep -q '^running' jobs/highgate-cohort-1126.status 2>/dev/null \
   || grep -q '^running' jobs/ridegate-live-render-holdout-3.status 2>/dev/null; do
  echo "waiting for render slot $(date +%T)"
  sleep 60
done
echo "render slot free at $(date)"
unset PICKER_STYLE_GATED PICKER_STYLE_GATED_MAP PICKER_INJECT_CS PICKER_WIN RIDEGATE RIDEGATE_PACK LINGER_GUARD
export PYTHONUNBUFFERED=1
export WORKERS="${WORKERS:-2}"
R=protrans/replica
python3 - <<'PY'
import json, sys
sys.path.insert(0, '/workspace/mixes/protrans')
import paths
r = json.load(open(paths.RULES))
assert not r.get('RIDEGATE') and not r.get('LINGER_GUARD') and not r.get('PICKER_STYLE_GATED'), r
print('rules.json picker/linger flags off', paths.RULES)
PY

# Restore missing fresh-mix sources into a scratch EXTRA_SRC (not feat_lib).
SRC=/tmp/ridegate_fresh_src
mkdir -p "$SRC"
python3 - <<'PY'
import json, os, sys
sys.path.insert(0, '/workspace/mixes/protrans')
sys.path.insert(0, '/workspace/mixes/protrans/replica')
import paths, fetch
W = '/workspace/mixes/protrans/replica/nightly_1126_work'
FEAT = os.path.join(paths.ROOT, 'corpus_v2', 'features')
FLIB = os.path.join(paths.ROOT, 'corpus_v2', 'feat_lib')
SRC = '/tmp/ridegate_fresh_src'
pf = json.load(open(os.path.join(W, 'picker_1126_fresh.json')))
yts = {}
for p in pf['per_pair']:
    f = json.load(open(os.path.join(FEAT, p['id'] + '.json')))
    for tr in (f['track_a'], f['track_b']):
        yts[tr['yt']] = tr.get('url') or f"https://www.youtube.com/watch?v={tr['yt']}"
need = []
for yt, url in sorted(yts.items()):
    dest = os.path.join(SRC, yt + '.m4a')
    if os.path.exists(dest) and os.path.getsize(dest) > 10000:
        continue
    for root in (FLIB, paths.LIB, '/workspace/mixes/src2', '/workspace/mixes/protrans/replica/fresh_src'):
        src = os.path.join(root, yt + '.m4a')
        if os.path.exists(src) and os.path.getsize(src) > 10000:
            os.symlink(src, dest) if not os.path.exists(dest) else None
            # if dest missing, copy via link above; if exists skip
            break
    if not (os.path.exists(dest) and os.path.getsize(dest) > 10000):
        need.append((yt, url, dest))
print('fresh unique tracks', len(yts), 'already local', len(yts) - len(need), 'to fetch', len(need), flush=True)
ok, bad = 0, []
for yt, url, dest in need:
    try:
        print('FETCH', yt, flush=True)
        fetch.ytdlp_remote(url, dest, kind='audio')
        if os.path.exists(dest) and os.path.getsize(dest) > 10000:
            ok += 1
        else:
            bad.append(yt)
    except Exception as e:
        print('FETCH_FAIL', yt, type(e).__name__, e, flush=True)
        bad.append(yt)
print('FETCH_DONE ok', ok, 'fail', len(bad), 'have', sum(1 for yt in yts if os.path.exists(os.path.join(SRC, yt + '.m4a'))), flush=True)
if bad:
    print('MISSING', ','.join(bad), flush=True)
PY

export EXTRA_SRC="$SRC"
export ONLY="$(python3 -c 'import json; pp=json.load(open("/workspace/mixes/protrans/replica/nightly_1126_work/picker_1126_fresh.json"))["per_pair"]; print(",".join(p["id"] for p in pp))')"
echo "ONLY $ONLY"
# Unique ckpt names; eval_gate tags are unique per full variant.
# Clear leftover ckpts for a clean run.
rm -f /workspace/mixes/protrans/replica/gate_ckpt/n1126f_default.jsonl \
      /workspace/mixes/protrans/replica/gate_ckpt/n1126f_ridegate_live.jsonl \
      /workspace/mixes/protrans/replica/gate_ckpt/n1126f_ridegate_linger.jsonl
nice -n 10 python3 $R/eval_gate.py \
  'n1126f_default={}' \
  'n1126f_ridegate_live={"RIDEGATE":1}' \
  'n1126f_ridegate_linger={"RIDEGATE":1,"LINGER_GUARD":1}'
nice -n 10 python3 $R/compare_ridegate_fresh.py
# Confirm rules.json untouched
python3 - <<'PY'
import json, hashlib, sys
sys.path.insert(0, '/workspace/mixes/protrans')
import paths
r = json.load(open(paths.RULES))
assert not r.get('RIDEGATE') and not r.get('LINGER_GUARD')
print('rules.json still has picker/linger flags off')
PY
echo "ALLDONE $(date)"
