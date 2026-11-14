#!/usr/bin/env bash
# Mix 09 r6 (P1 root cause): the 320k MP3 overshoot (-0.6/-0.7 dBTP at the standard gain 9.3, limiter WAV at -2.1 dBTP everywhere) sits
# only on Etherwood - Sinking Sand (YFMvngI33oE) passages: 70-200x more energy above 16 kHz than the rest of the mix, which the LAME
# lowpass/filterbank turns into ~1.3 dB inter-sample overshoot (0.3-0.7 dB elsewhere). Mastering chain unchanged; swap that track
# (repair replace, tests untouched) and render at the standard gain 9.3. r5 (gain 8.0, -10.2 LUFS) stays as the passing fallback.
set -uo pipefail
cd /workspace/mixes/src2; . ../mix09/env09.sh
which rubberband rsync >/dev/null || { echo "missing rubberband/rsync"; exit 1; }
grep -vx YFMvngI33oE <(tr ' ' '\n' < ../mix09/crate.txt | grep .) | tr '\n' ' ' > ../mix09/crate_r6.txt
python3 -u repair.py --plan plan_mix09_r5.json --out plan_mix09_r6.json --culprit 'I9QGpHScGug>YFMvngI33oE:P1' \
  --history mix09_r3,mix09_r4 --table pair_table_09r3.json --crate ../mix09/crate_r6.txt --tag mix09r6_ --budget-s 1800 --max-dry 150 \
  --rounds 2 --render-name mix09_r6 --gain 9.3 --nudge nudge08_r9c.json --render-script ../mix09/render09.sh
