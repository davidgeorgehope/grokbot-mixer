# Mix 08 progress
Ad hoc build started 2026-11-09 16:44 ET (America/New_York). Env: STRUCT=1 FADE=tail LOOP32=0 ECHO_MAX=2 PREF_W=0 SWAP_PHRASE=1 HIGH_SWAP=1 BASS_SWAP_BARS=2. Master gain 9.3 start.

- 16:44 ET: [08] Fetched 1991 & Grace Barton – Stars Align (UKF official, LJJ4cJzpjKk) on residential machine, chrome cookies OK. add_track running.
- 16:46 ET: [08] Stars Align prepped: 174.001 BPM (radio edit 3:32, 154 bars), key 3B (Db major per Beatport; bgate/krumhansl agree). Added to keys_extra.
- 16:50 ET: [08] Crate of 30 restored (mix08/crate.txt; 26 not in Mix 07). plan_search r0 started (open order, SOFT=0, DROP_FRAC=0.3, PINW gold Lilies>JHO, require it, PREV_PLANS=mix07r17).
- 16:52 ET: [08] plan_search r0 failed: missing st/LJJ4cJzpjKk.onset.npy (new tracks only had wav/json; pair_feats.build did a raw load). Added src2/onsets.py, pair_feats.build and mix_simple.onsets now call onsets.ensure, add_track.sh writes the cache at prep. Generated the Stars Align file (154 bars). Rerunning as search-mix08-r1.
