#!/bin/bash
cd /workspace/mixes/protrans || exit 1
HC=HC_A python3 replica/final_eval.py && cp replica/final_eval_dev.json replica/final_eval_dev_HC_A.json && \
HC=HC_B python3 replica/final_eval.py && cp replica/final_eval_dev.json replica/final_eval_dev_HC_B.json
