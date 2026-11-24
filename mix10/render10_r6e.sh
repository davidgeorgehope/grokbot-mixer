#!/usr/bin/env bash
# Mix 10 r6e: repair r6c render faults with fair per-pair budget (round-robin +
# first-try guarantee), then dry + render at gain 9.0. Remaster at 8.0 only if
# true-peak is the remaining fail. Does not loosen checks.
# budget-s is 10800 (3h): r6d's 1800s ran out after five ~10 min dries, before
# the last three pairs were tried. Thresholds are unchanged.
set -uo pipefail
export PYTHONUNBUFFERED=1
cd /workspace/mixes/src2
_CRATE=${CRATE_FILE:-/workspace/mixes/mix10/crate_r5.txt}
_TABLE=${PAIR_TABLE:-pair_table_10r6.json}
. /workspace/mixes/mix10/env10.sh
export CRATE_FILE="$_CRATE" PAIR_TABLE="$_TABLE"

echo "=== repair mix10_r6c -> plan_mix10_r6e.json ==="
python3 repair.py --plan plan_mix10_r6c.json --out plan_mix10_r6e.json --render mix10_r6 \
  --budget-s 10800 --max-dry 150 --tag r6e
rc=$?
if [ "$rc" != 0 ]; then
  echo "REPAIR FAILED rc=$rc — partial plan/hist may be in plan_mix10_r6e.json and plan_mix10_r6e.hist.json"
  exit 2
fi
if [ ! -f plan_mix10_r6e.json ]; then
  echo "REPAIR FAILED rc=$rc — no plan_mix10_r6e.json"
  exit 2
fi

echo "=== render plan_mix10_r6e.json at gain 9.0 ==="
bash /workspace/mixes/mix10/render10.sh plan_mix10_r6e.json mix10_r6e mix10_r6e.mp3 9.0
rc=$?
if [ "$rc" = 0 ]; then
  echo "RENDER ALL-PASS at gain 9.0"
  exit 0
fi

# remaster at 8.0 only when true-peak / P1 is the remaining audio fail
python3 - <<'PY'
import json,sys,re
from pathlib import Path
g=json.load(open('guard_mix10_r6e/guardrails.json')) if Path('guard_mix10_r6e/guardrails.json').exists() else {}
fails=[f.get('check') for f in g.get('failures') or []]
log=(Path('guard_mix10_r6e/pytest.log').read_text() if Path('guard_mix10_r6e/pytest.log').exists() else '')
# pytest names that failed
py=re.findall(r'^FAILED .*/(test_\w+)\.py::(\w+)', log, re.M)
py_names=[b for a,b in py] if py else re.findall(r'FAILED .*::(\w+)', log)
print('guardrail fails', fails)
print('pytest fails', py_names)
ok_py={'test_true_peak','test_guardrails_zero_failures'}
ok_g={'P1'}
only_tp=fails and set(fails)<=ok_g and py_names and set(py_names)<=ok_py
# also allow pytest-only TP if guardrails missing
if not fails and set(py_names)<=ok_py and 'test_true_peak' in py_names:
    only_tp=True
sys.exit(0 if only_tp else 3)
PY
tp=$?
if [ "$tp" != 0 ]; then
  echo "RENDER FAILED with non-peak faults (rc=$rc) — not remastering"
  exit 1
fi

echo "=== remaster at gain 8.0 (true-peak only remaining fail) ==="
bash /workspace/mixes/src/master.sh mix10_r6e_raw.wav mix10_r6e.mp3 8.0 mix10_r6e_master.wav || exit 1
python3 cleanup_round_wavs.py mix10_r6e || true
python3 ../src/guardrails.py --name mix10_r6e --mp3 mix10_r6e.mp3 --nudge "${NUDGE:-nudge08_r9c.json}" --png 2>&1 | grep -vE "Warning|m=np"
G=${PIPESTATUS[0]}
mkdir -p guard_mix10_r6e
MIX_NAME=mix10_r6e MIX_MP3=mix10_r6e.mp3 MIX_WAV="/workspace/mixes/src2/mix10_r6e_master.wav" \
  python3 -m pytest -q -p no:cacheprovider ../src/tests ../src/build_qa > guard_mix10_r6e/pytest.log 2>&1
P=$?
tail -25 guard_mix10_r6e/pytest.log
python3 cue_report.py mix10_r6e_meta.json --json guard_mix10_r6e/pro_likeness.json || true
echo "RESULT remaster8 guardrails_exit=$G pytest_exit=$P"
[ "$G" = 0 ] && [ "$P" = 0 ]
