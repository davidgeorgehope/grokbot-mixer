#!/usr/bin/env bash
# Build pair_table_10r5.json for crate_r5, then start search-mix10-r5.
set -euo pipefail
J=/workspace/mixes/jobs
echo "building pair_table_10r5.json $(date -Is)"
cd /workspace/mixes/src2
set -a
. /workspace/mixes/mix10/env10.sh
set +a
export CRATE_FILE=/workspace/mixes/mix10/crate_r5.txt
export PAIR_TABLE=pair_table_10r5.json
python3 -u plan_search.py table --base plan_mix10_base.json
ls -l pair_table_10r5.json
python3 -c "import json;T=json.load(open('pair_table_10r5.json'));print('built_s',T['built_s'],'tracks',len(T['tracks']),'pairs',len(T['pairs']))"
# sanity: Afterglow>Meteorites chosen r4 window must not be voc=0
python3 - <<'PY'
import json
T=json.load(open('pair_table_10r5.json'))
k='I9QGpHScGug>SqzxwPEa-DI'
w=['la',112,None,64,16] if False else ['la',112,96,64,16]
rec=T['pairs'].get(k)
if not rec:
    print(k,'not in table (ok if Afterglow or Meteorites dropped)')
else:
    hits=[x for x in rec['wins'] if list(x['w'])==w]
    voc_n=sum(1 for x in rec['wins'] if x.get('voc'))
    print(k,'voc_wins',voc_n,'chosen',hits[0] if hits else 'not in topK')
    if hits and hits[0]['voc']==0:
        raise SystemExit('Afterglow>Meteorites r4 window still voc=0 after table rebuild')
print('table sanity ok')
PY
echo "starting search-mix10-r5 $(date -Is)"
exec $J/runjob.sh search-mix10-r5 nice -n 15 ionice -c 2 -n 7 bash /workspace/mixes/mix10/search10_r5.sh
