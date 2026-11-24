#!/usr/bin/env bash
# Mix 10 r6g: r6e order, Together>In The Night already gated at ['n',240,None,48,16].
# When My Love intro bars 15-27 have a +19.1 ms source offset (n1_grid_align) so the
# ib=16 cue is on the N1 grid. Re-gate that pair, then full dry + render at gain 9.0.
# Remaster at 8.5 only if true-peak / P1 is the remaining fail. Does not loosen checks.
set -uo pipefail
export PYTHONUNBUFFERED=1
cd /workspace/mixes/src2
_CRATE=${CRATE_FILE:-/workspace/mixes/mix10/crate_r5.txt}
_TABLE=${PAIR_TABLE:-pair_table_10r6.json}
. /workspace/mixes/mix10/env10.sh
export CRATE_FILE="$_CRATE" PAIR_TABLE="$_TABLE"
export NUDGE="${NUDGE:-nudge08_r9c.json}" GAIN="${GAIN:-9.0}"
export BLEND_AUDIO_GATE=1
export PYTHONPATH="/workspace/mixes/src2:/workspace/mixes/src/tests:/workspace/mixes/src/build_qa${PYTHONPATH:+:$PYTHONPATH}"

echo "=== gate alternate windows for the the remaining When My Love blend after the intro-grid offset ==="
python3 /workspace/mixes/mix10/gate_r6g_alts.py
rc=$?
if [ "$rc" != 0 ] || [ ! -f plan_mix10_r6g.json ]; then
  echo "GATE/PLAN FAILED rc=$rc — see /workspace/mixes/mix10/gate_r6g_alts_results.json"
  exit 2
fi

echo "=== dry-confirm plan_mix10_r6g.json ==="
python3 - <<'PY'
import json,sys,os
os.chdir('/workspace/mixes/src2')
sys.path.insert(0,'/workspace/mixes/src2')
sys.path.insert(0,'/workspace/mixes/src/tests')
sys.path.insert(0,'/workspace/mixes/src/build_qa')
import plan_search as PS
r=PS.dry(json.load(open('plan_mix10_r6g.json')),'r6g')
print(json.dumps({k:r.get(k) for k in ('all_ok','len_min','tests','warn','error')},indent=1,default=str))
# print per-test
tests=r.get('tests') or {}
bad=[k for k,v in tests.items() if v is False]
print('failed dry tests:', bad or 'none')
sys.exit(0 if r.get('all_ok') and not bad else 2)
PY
rc=$?
if [ "$rc" != 0 ]; then
  echo "FULL DRY FAILED rc=$rc — not rendering"
  exit 2
fi

echo "=== render plan_mix10_r6g.json at gain 9.0 ==="
bash /workspace/mixes/mix10/render10.sh plan_mix10_r6g.json mix10_r6g mix10_r6g.mp3 9.0
rc=$?
if [ "$rc" = 0 ]; then
  echo "RENDER ALL-PASS at gain 9.0"
  exit 0
fi

python3 - <<'PY'
import json,sys,re
from pathlib import Path
g=json.load(open('guard_mix10_r6g/guardrails.json')) if Path('guard_mix10_r6g/guardrails.json').exists() else {}
fails=[f.get('check') for f in g.get('failures') or []]
log=(Path('guard_mix10_r6g/pytest.log').read_text() if Path('guard_mix10_r6g/pytest.log').exists() else '')
py=re.findall(r'^FAILED .*/(test_\w+)\.py::(\w+)', log, re.M)
py_names=[b for a,b in py] if py else re.findall(r'FAILED .*::(\w+)', log)
print('guardrail fails', fails)
print('pytest fails', py_names)
ok_py={'test_true_peak','test_guardrails_zero_failures'}
ok_g={'P1'}
only_tp=bool(py_names) and set(py_names)<=ok_py and (not fails or set(fails)<=ok_g)
if not fails and set(py_names)<=ok_py and 'test_true_peak' in py_names:
    only_tp=True
sys.exit(0 if only_tp else 3)
PY
tp=$?
if [ "$tp" != 0 ]; then
  echo "RENDER FAILED with non-peak faults (rc=$rc) — not remastering"
  exit 1
fi

echo "=== remaster at gain 8.5 (true-peak only remaining fail) ==="
bash /workspace/mixes/src/master.sh mix10_r6g_raw.wav mix10_r6g.mp3 8.5 mix10_r6g_master.wav || exit 1
python3 cleanup_round_wavs.py mix10_r6g || true
python3 ../src/guardrails.py --name mix10_r6g --mp3 mix10_r6g.mp3 --nudge "${NUDGE:-nudge08_r9c.json}" --png 2>&1 | grep -vE "Warning|m=np"
G=${PIPESTATUS[0]}
mkdir -p guard_mix10_r6g
MIX_NAME=mix10_r6g MIX_MP3=mix10_r6g.mp3 MIX_WAV="/workspace/mixes/src2/mix10_r6g_master.wav" \
  python3 -m pytest -q -p no:cacheprovider ../src/tests ../src/build_qa > guard_mix10_r6g/pytest.log 2>&1
P=$?
tail -25 guard_mix10_r6g/pytest.log
python3 cue_report.py mix10_r6g_meta.json --json guard_mix10_r6g/pro_likeness.json || true
echo "RESULT remaster8.5 guardrails_exit=$G pytest_exit=$P"
[ "$G" = 0 ] && [ "$P" = 0 ]
