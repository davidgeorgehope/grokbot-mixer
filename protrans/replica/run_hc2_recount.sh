#!/bin/bash
cd /workspace/mixes/protrans || exit 1
python3 replica/hc2_recount.py default on gated dropx && python3 replica/online_hc2.py
