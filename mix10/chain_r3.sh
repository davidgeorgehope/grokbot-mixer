#!/usr/bin/env bash
# After vocfix-mix10-r3: rebuild pair table, stop the doomed r2 search, start r3 search.
set -euo pipefail
J=/workspace/mixes/jobs
# wait for vocfix
while grep -q '^running' $J/vocfix-mix10-r3.status 2>/dev/null; do sleep 20; done
grep -q '^done' $J/vocfix-mix10-r3.status || { echo "vocfix not done: $(cat $J/vocfix-mix10-r3.status)"; exit 1; }

# confirm voc still present (nightly must not have stripped it)
python3 - <<'PY'
import json,sys
ids=['EpHrodtTiK0','I9QGpHScGug','SqzxwPEa-DI','zEvLsOVhg0I','J3oTRY7AdE4']
for b in ids:
    g=json.load(open(f'/workspace/mixes/src2/st/{b}.json'))['bar']
    if 'voc' not in g:
        print('voc missing after vocfix wait:', b); sys.exit(1)
print('voc still present for', ids)
PY

echo "building pair_table_10r3.json $(date -Is)"
cd /workspace/mixes/src2
set -a
. /workspace/mixes/mix10/env10.sh
set +a
export CRATE_FILE=/workspace/mixes/mix10/crate_r2.txt
export PAIR_TABLE=pair_table_10r3.json
# drop a stale file with the same name if a previous key wouldn't match anyway
python3 -u plan_search.py table --base plan_mix10_base.json
ls -l pair_table_10r3.json
python3 -c "import json;T=json.load(open('pair_table_10r3.json'));print('built_s',T['built_s'],'tracks',len(T['tracks']),'pairs',len(T['pairs']))"

# stop r2 if still running (same Logistics chain, table blind to the now-fixed vocals)
if grep -q '^running' $J/search-mix10-r2.status 2>/dev/null; then
  echo "stopping search-mix10-r2 so r3 can start"
  # runjob is the parent; the python search is its child
  p=$(pgrep -f 'plan_search.py search --base plan_mix10_base.json --out plan_mix10_r2.json' || true)
  if [ -n "$p" ]; then
    kill $p || true
    # wait until runjob writes failed/done
    for i in $(seq 1 30); do
      grep -qv '^running' $J/search-mix10-r2.status 2>/dev/null && break
      sleep 2
    done
  fi
  echo "r2 status now: $(cat $J/search-mix10-r2.status)"
fi

echo "starting search-mix10-r3 $(date -Is)"
exec $J/runjob.sh search-mix10-r3 nice -n 15 ionice -c 2 -n 7 bash /workspace/mixes/mix10/search10_r3.sh
