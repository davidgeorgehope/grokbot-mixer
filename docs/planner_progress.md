# Planner (plan everything before rendering) - progress
- 21:10 local: src2/plan_search.py started. predict(name) = every meta-only test target via the tests' own functions + level-model E4.
  E4 on predicted levels calibrated on 12 renders: 10 dB / >12 bars separates the 3 E4 fails (mixLen1, mixLen3, mixT; 22-bar runs) from the 9 passes (<=10).
  mix_simple: opt-in plan key out_win (planner's chosen window per blend; absent = unchanged behaviour).
- pair table building (nohup, /workspace/plan/table.log).
- 21:20 table built: 50 tracks, 2450 ordered pairs, 432 key-compatible with top-40 windows, 197 s. validate: E4 predicted 12/12 renders; dry(plan_60k21)==mixLen21b meta 20/20 decks 19/19 blends. search running (/workspace/plan/search.log).
- 21:55 search v1: table-predicted per-blend drum runs, coverage, length == dry exactly; E4 missed a blend dip -> table now stores per-bar blend levels, search checks lulls across blends too. Rebuilding table + search.
