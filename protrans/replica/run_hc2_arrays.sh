#!/bin/bash
cd /workspace/mixes/protrans || exit 1
python3 replica/hc2_arrays.py must1117_nolock kush_default kush_gated kush_on kush_dropx kush_dropc dropc default gated on dropx
