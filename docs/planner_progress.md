# Planner (plan everything before rendering) - progress
- 21:10 local: src2/plan_search.py started. predict(name) = every meta-only test target via the tests' own functions + level-model E4.
  E4 on predicted levels calibrated on 12 renders: 10 dB / >12 bars separates the 3 E4 fails (mixLen1, mixLen3, mixT; 22-bar runs) from the 9 passes (<=10).
  mix_simple: opt-in plan key out_win (planner's chosen window per blend; absent = unchanged behaviour).
- pair table building (nohup, /workspace/plan/table.log).
- 21:20 table built: 50 tracks, 2450 ordered pairs, 432 key-compatible with top-40 windows, 197 s. validate: E4 predicted 12/12 renders; dry(plan_60k21)==mixLen21b meta 20/20 decks 19/19 blends. search running (/workspace/plan/search.log).
- 21:55 search v1: table-predicted per-blend drum runs, coverage, length == dry exactly; E4 missed a blend dip -> table now stores per-bar blend levels, search checks lulls across blends too. Rebuilding table + search.
- 2026-11-15: src2/window_planner.py (off by default). Nominates mid-track section windows and chooses per pair from track features, with SNAP_IN only for breakdown-into-drop. See docs/PLANNER_2026-11-15.md.
- 2026-11-15 later: wp1115 cohort finished, 0 fails, train 32.65 / held-out 34.03 vs floor 34.05. Flag stays off. Both 11-14 and 11-15 targets hit their planned windows. Clips in deliver/protrans/planner_2026-11-15_*.mp3.
- 2026-11-15 v2: dropped BASS_COVER fallback; breakdown_drop with 3+ incoming drops prefers the last-drop +32 body phrase; SNAP_IN_HOLD when the outgoing has runway. ukf__25 window [n, 128, None, 192, 16]. Clip planner_2026-11-15_ukf25_v2.mp3. Cohort wp1115v2.
- 2026-11-15 v2 later: wp1115v2 cohort 0 fails, train 31.60 / held-out 30.97 vs floor 34.05. Flag stays off. ukf__25 window [n, 128, None, 192, 16] SNAP_IN_HOLD. Clip trimmed to 49.66 s at -14 LUFS, tick 0:11.
