#!/usr/bin/env bash
# JOINT_PICKER render check: dev-27 (official v1/v2 + hard checks; in-sample for the picker) then the
# 18-pair fresh ukf mix (hard checks; baseline n1126f_rgdef = current default). Run a /tmp copy of this file.
main() {
  set -euo pipefail
  cd /workspace/mixes/protrans/replica
  export PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1
  PFW=3 python3 measure_joint_1127.py r1
  export EXTRA_SRC=/tmp/ridegate_fresh_src WORKERS=3
  export ONLY="$(python3 -c 'import json; pp=json.load(open("/workspace/mixes/protrans/replica/nightly_1126_work/picker_1126_fresh.json"))["per_pair"]; print(",".join(p["id"] for p in pp))')"
  rm -f gate_ckpt/n1127f_joint_r1.jsonl
  python3 eval_gate.py 'n1127f_joint_r1={"JOINT_PICKER":1}'
  echo ALLDONE
}
main "$@"; exit $?
