#!/usr/bin/env bash
cd /workspace/mixes/protrans
ONLY="$(cat /tmp/gp_ids.txt)" WORKERS=2 python3 replica/eval_gate.py 'gcover={"REPLICA":"gated","BASS_COVER":1}' 'gx32={"REPLICA":"gated","REPLICA_X":32}'
